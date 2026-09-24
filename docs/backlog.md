# Initial task backlog

Use these tasks to seed the linked GitHub Project. The service allocation and stack are confirmed. API and gameplay details are proposed and need review before implementation.

The remaining work is also published as [repository issues #1–12](https://github.com/MadalinaDev/tamagotchi-go-team-12/issues). Lab 0 follow-ups are #1–7; future planning is #8–12. Sava's private READMEs and two real submodules have been prepared; Vica's Guild and Notification private READMEs and two real submodules are also prepared. The remaining four repository links are still pending. Mădălina can add the issues to the Project without recreating them.

| Milestone | Task | Owner | Acceptance criteria |
| --- | --- | --- | --- |
| Lab 0 | Review common architecture and cross-service contracts | All four | Each owner reviews their APIs, dependencies, data ownership and request/response/event types; disagreements resolved in a PR |
| Lab 0 | Enable shared branch protection | Mădălina | main/dev require one approval, resolved reviews and PR policy; force pushes/deletion blocked |
| Lab 0 | Create/link Project and assign tasks | Mădălina / Project owner | Board is accessible to team, linked to repository and populated with tasks |
| Lab 0 | Publish Battle and Tamagotchi READMEs and submodules | Sava | Relevant contracts copied; pointers resolve to pushed private commits |
| Lab 0 | Publish Guild and Notification READMEs and submodules | Vica | Supply both URLs, copy relevant contracts and link commits |
| Lab 0 | Publish User Management and Map READMEs and submodules | Mădălina | Relevant contracts copied; pointers resolve to pushed private commits |
| Lab 0 | Publish Monster Raid and Package Registry READMEs and submodules | Sabina | Supply both URLs, copy relevant contracts and link commits |
| Lab 0 | Complete professor invitations, Excel and presentation signup | All four | Professor access verified, repository/team data entered, presentation slot reserved |
| Next lab planning | Scaffold Battle and Tamagotchi services | Sava | Go projects, isolated PostgreSQL databases, validated DTOs and documented local launch |
| Next lab planning | Implement reservations and PvP state transitions | Sava | Concurrent pet-use protection, turn validation, package-specific snapshots and exactly-once business effects tested |
| Next lab planning | Scaffold Guild and Notification services | Vica | Go projects; guild membership/chat contracts and Firebase delivery setup ready |
| Next lab planning | Implement chat recovery and notification deduplication | Vica | Membership enforcement, persisted history and duplicate delivery scenarios tested |
| Next lab planning | Scaffold User Management and Map services | Mădălina | NestJS + Prisma projects; isolated PostgreSQL/PostGIS databases; auth and location DTOs |
| Next lab planning | Implement wallet settlement and proximity state | Mădălina | No negative balances/duplicate rewards; stale locations and repeated encounter events handled |
| Next lab planning | Scaffold Monster Raid and Package Registry services | Sabina | NestJS + Prisma projects, immutable definition schemas and scheduler persistence |
| Next lab planning | Implement raid lifecycle and package care definitions | Sabina | Cancel/activate races, reward cleanup, package-specific bonus interpretation tested |
| Next lab planning | Agree shared local infrastructure and integration scenarios | All four | Database credentials isolated, RabbitMQ outbox/inbox convention tested, example clients can exercise service interactions |

Future implementation tasks are planning suggestions, **not claims about the next lab's grading rubric**. Revise them when that assignment is released.
