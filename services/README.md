# Private service submodules

The directories here are Git submodules pointing to commits in individually owned private repositories. Their source and README files are stored in those repositories, not copied into this public repository.

Initialize only repositories you can access:

```sh
git submodule update --init services/battle-service services/tamagotchi-service services/guild-service services/notification-service services/user-management-service services/map-service services/monster-raid-service services/package-registry-service services/gateway-service
```

The professor(s) need invitations to each private repository to inspect a full recursive checkout. Teammates retain access only to their own private services; shared contracts remain in the [public README](../README.md). The exception is `gateway-service` (Lab 2), which the whole team works on: every teammate is a collaborator.

These private repositories are published on GitHub as private repos and linked as submodules from the public CPR.

See the [repository table](../README.md#repository-setup-and-lab-0-checklist) for the current service URLs and setup status.
