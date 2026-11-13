// Guild chat across replicas: several sockets are opened on port 8083 (the
// guild-ws proxy hands the connections to the Guild replicas in turn), one
// message is sent over REST, and every socket must receive it, whichever
// replica holds it.
// Usage: GATEWAY_SECRET=<from .env> [GUILD=http://localhost:8083] [SOCKETS=4] go run .
// Then: docker compose logs guild-service | grep chat.connected
// shows which replica took each socket.
package main

import (
	"bytes"
	"crypto/rand"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"strconv"
	"sync"
	"time"

	"github.com/gorilla/websocket"
)

const guild = "00000000-0000-4000-8000-0000000000c1"
const alice = "00000000-0000-4000-8000-000000000001"
const bob = "00000000-0000-4000-8000-000000000002"

func env(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}

// newID is a random version 4 UUID: Guild rejects a reused client_message_id.
func newID() string {
	b := make([]byte, 16)
	rand.Read(b)
	b[6] = b[6]&0x0f | 0x40
	b[8] = b[8]&0x3f | 0x80
	return fmt.Sprintf("%x-%x-%x-%x-%x", b[0:4], b[4:6], b[6:8], b[8:10], b[10:])
}

func post(base, user, path string, body any) map[string]any {
	raw, _ := json.Marshal(body)
	req, _ := http.NewRequest(http.MethodPost, base+path, bytes.NewReader(raw))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Gateway-Secret", os.Getenv("GATEWAY_SECRET"))
	req.Header.Set("X-Auth-User-Id", user)
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		panic(err)
	}
	defer resp.Body.Close()
	var out map[string]any
	json.NewDecoder(resp.Body).Decode(&out)
	fmt.Println("POST", path, "->", resp.StatusCode)
	return out
}

func main() {
	base := env("GUILD", "http://localhost:8083")
	n, _ := strconv.Atoi(env("SOCKETS", "4"))

	var ready, done sync.WaitGroup
	received := make([]bool, n)
	for i := 0; i < n; i++ {
		t := post(base, alice, "/api/v1/guilds/"+guild+"/chat-tickets", map[string]any{})
		ws, resp, err := websocket.DefaultDialer.Dial("ws"+base[4:]+"/api/v1/guilds/"+guild+"/ws?ticket="+t["ticket"].(string), nil)
		if err != nil {
			fmt.Println("socket", i+1, "failed:", err, resp)
			os.Exit(1)
		}
		fmt.Println("socket", i+1, "->", resp.StatusCode)
		ready.Add(1)
		done.Add(1)
		go func(i int) {
			defer done.Done()
			ready.Done()
			ws.SetReadDeadline(time.Now().Add(5 * time.Second))
			for {
				_, msg, err := ws.ReadMessage()
				if err != nil {
					return
				}
				var f struct{ Type string }
				if json.Unmarshal(msg, &f) == nil && f.Type == "chat.message" {
					received[i] = true
					return
				}
			}
		}(i)
	}
	ready.Wait()
	time.Sleep(300 * time.Millisecond)
	post(base, bob, "/api/v1/guilds/"+guild+"/messages", map[string]any{"text": "hello from the demo", "client_message_id": newID()})
	done.Wait()

	ok := 0
	for i, r := range received {
		fmt.Printf("socket %d received chat.message: %v\n", i+1, r)
		if r {
			ok++
		}
	}
	if ok != n {
		fmt.Printf("FAIL: %d of %d sockets received the message\n", ok, n)
		os.Exit(1)
	}
	fmt.Printf("OK: all %d sockets received the message\n", n)
}
