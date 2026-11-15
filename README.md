# EventSphere

A mobile-friendly venue booking and digital ticketing platform in which **every booking decision is made by cooperating software agents**.
Built for *IT4123 Agent Based Computing Practical, ICA 02*.

- **Live site:** eventsphere-production-2031976c.up.railway.app   
- **Repository:** https://github.com/ridmisamarasundara/EventSphere 

Attendees browse events, book tickets from their phone and walk in with a QR code. The same venues can be hired whole for private occasions.
Payments are **simulated**: no bank, card or payment gateway is used and no card details are ever collected.

---

## Features

| Role | What they can do |
|---|---|
| **Attendee** | Register and sign in, search and filter events, book and cancel tickets (with a stated refund policy), see QR tickets, join waitlists with timed seat holds, request private venue hire, read notifications |
| **Gate staff** | Scan tickets with the phone camera, or type the code manually. Each ticket is admitted once only |
| **Admin / organiser** | Create and edit venues and events (draft, publish, cancel), approve or reject venue hire requests, see sales, revenue, check-ins and charts, read the agent message log |

### The five agents

| Agent | Goal | Decides on its own |
|---|---|---|
| **VenueAgent** | Keep every venue calendar free of clashes | Accept or refuse an event slot (30-minute turnaround buffer), confirm / escalate / counter-propose a private hire, price a hire |
| **BookingAgent** | Sell tickets fairly without overselling | Accept or refuse a ticket request, refund amount on cancellation, full refunds when an event is cancelled |
| **TicketAgent** | Admit each ticket exactly once | Issue unique codes; admit, already used, wrong event, cancelled, or outside check-in time |
| **WaitlistAgent** | Pass freed seats to waiting customers | Who gets released seats, hold them for 15 minutes, expire unclaimed holds and re-offer them on a timer |
| **NotificationAgent** | Tell the right person what affects them | Turns events from other agents into user notifications |

Agents never call each other's functions. They exchange **JSON messages** (sender, receiver, performative, content, conversation id) through a message bus, and every message is logged and shown on the admin **Agent log** page.
The numbered decision rules of each agent are written at the top of its file in `app/agents/`.

---

## Tech stack

| Part | Technology |
|---|---|
| Backend | Python 3.11+, FastAPI |
| Validation | Pydantic |
| Database | PostgreSQL in production, SQLite for local development (SQLAlchemy) |
| Agent messaging | JSON messages over an in-process message bus |
| Timer | APScheduler (WaitlistAgent expiry sweep every 30 seconds) |
| Frontend | HTML, CSS, JavaScript, Bootstrap 5, Chart.js, html5-qrcode. Works at 375 px phone width |
| QR codes | `qrcode` (Python) |
| Tests | Pytest |
| Hosting | Railway (HTTPS) |

---

## Project structure

```
eventsphere/
├── app/
│   ├── main.py            FastAPI app, middleware, startup (agents, timer, demo data)
│   ├── config.py          environment variables
│   ├── database.py        SQLAlchemy engine and session
│   ├── security.py        bcrypt hashing and CSRF protection
│   ├── deps.py            login and role checks, flash messages
│   ├── schemas.py         Pydantic validation for forms
│   ├── agent_client.py    how web routes send messages to the agents
│   ├── seed.py            demo accounts and sample data
│   ├── templating.py      Jinja2 setup and filters
│   ├── agents/            message bus, the five agents, timer
│   ├── models/            database models
│   ├── routes/            web pages and the scan API
│   ├── templates/         HTML templates
│   └── static/            CSS and JavaScript
├── tests/                 Pytest suite
├── seed.py                optional: create demo data from the command line
├── requirements.txt
├── .env.example
└── README.md
```

---

## Run locally

**Requirements:** Python 3.11 or newer and Git.

**Windows (Command Prompt or VS Code terminal)**

```
git clone https://github.com/YOUR-USERNAME/eventsphere.git
cd eventsphere
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

**macOS / Linux**

```
git clone https://github.com/YOUR-USERNAME/eventsphere.git
cd eventsphere
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Open `.env` and put your own random value in `SECRET_KEY`. You can generate one with:

```
python -c "import secrets; print(secrets.token_hex(32))"
```

Start the server:

```
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000. With `SEED_DEMO=true` in `.env` the demo accounts and three sample events are created automatically on startup.
(You can also run `python seed.py` once.) The database file `eventsphere.db` is created next to the code.

---

## Environment variables

| Variable | Purpose | Default |
|---|---|---|
| `DATABASE_URL` | Database connection. SQLite locally, PostgreSQL in production. `postgres://` URLs are converted automatically | `sqlite:///./eventsphere.db` |
| `SECRET_KEY` | Signs session cookies. **Required in production**: the app refuses to start with the default value when `APP_ENV=production` | `dev-only-secret` |
| `APP_ENV` | `development`, `production` or `test`. `production` makes session cookies HTTPS-only | `development` |
| `SEED_DEMO` | `true` creates the demo accounts and sample data on startup (safe to leave on: it only creates what is missing) | `false` |
| `TZ_OFFSET_MINUTES` | Local venue time offset from UTC in minutes. Sri Lanka = `330` | `330` |
| `PORT` | Set automatically by the host and used in the start command | n/a |

Secrets live in environment variables. `.env` is listed in `.gitignore` and is never committed. Only `.env.example` is in the repository.

---

## Demo accounts

| Role | Email | Password |
|---|---|---|
| Admin | `admin@eventsphere.test` | `Admin@12345` |
| Staff | `staff@eventsphere.test` | `Staff@12345` |
| Attendee | `attendee@eventsphere.test` | `Attendee@12345` |

Anyone can register as an **attendee**. Admin and staff accounts cannot be created from the registration form (the role is never read from the form).

---

## Run the tests

```
pytest
```

The suite has **103 tests** and uses SQLite. `APP_ENV=test` is set by `tests/conftest.py`, which keeps the background timer off during tests.

| File | What it covers |
|---|---|
| `test_bus.py` | message format, reasons on every refusal, logging, broadcast, state surviving a restart |
| `test_venue_agent.py` | event clashes, turnaround buffer, capacity, hire confirm / escalate / counter-propose, weekend price |
| `test_booking_agent.py` | **overbooking**, ticket limits, refund policy, cancellation, event cancellation |
| `test_ticket_agent.py` | **double check-in**, wrong event, cancelled ticket, check-in window, suspicious scans |
| `test_waitlist_agent.py` | queue order, held seats, claim, **timer expiry and re-offer** |
| `test_notification_agent.py` | broadcast events become notifications |
| `test_auth_web.py`, `test_admin_web.py` | hashing, CSRF, role checks, venue / event management, hire approval, dashboard, agent log |
| `test_attendee_web.py`, `test_staff_web.py`, `test_ui_web.py` | search, booking flow, QR codes, waitlist, venue hire, scanner API, layout |

---

## A quick tour

1. Sign in as **admin**. Open **Admin → Events → New event**, add a ticket category and publish.
   Try an event that overlaps another one at the same venue: VenueAgent refuses it and explains why.
2. Sign in as **attendee** (use a second browser or a private window). Book tickets. You get a payment reference and a QR code for every ticket.
3. Sign in as **staff** and open **Scanner**. Choose the event, press *Start camera* (or paste the ticket code under *Show code*). The second scan of the same ticket is rejected.
   Tickets are only admitted from 2 hours before the event starts, so create an event that starts within the next hour to try this.
4. Sold out? Join the **waitlist** with a second account, then cancel the first booking. The seats are held for 15 minutes with a live countdown.
5. As admin, open **Agent log** and click a conversation id to follow one user action across several agents.

---

## Deploy on Railway

1. Push the repository to GitHub.
2. In Railway choose **New Project → Deploy from GitHub repo** and select the repository.
3. Add a database: **New → Database → Add PostgreSQL**.
4. Open the web service → **Variables** and add:

   | Variable | Value |
   |---|---|
   | `DATABASE_URL` | reference the PostgreSQL variable, for example `${{Postgres.DATABASE_URL}}` |
   | `SECRET_KEY` | a long random string |
   | `APP_ENV` | `production` |
   | `SEED_DEMO` | `true` |
   | `TZ_OFFSET_MINUTES` | `330` |

5. Open **Settings → Deploy** and set the start command (single worker, because the timer runs inside the web process):

   ```
   uvicorn app.main:app --host 0.0.0.0 --port $PORT
   ```

6. Open **Settings → Networking → Generate Domain** to get the public HTTPS address.
7. Check it: `https://YOUR-APP.up.railway.app/health` should show `{"status":"ok"}`, then log in with a demo account.

The camera scanner needs HTTPS, which Railway provides. Keep the service running and open the site before the viva.

---

## Security notes

- Passwords are hashed with bcrypt and never stored in plain text.
- Role checks on every admin and staff route (anonymous users go to the login page, wrong roles get 403).
- CSRF token on every state-changing request, including the scanner API.
- Sessions use signed cookies (`SameSite=Lax`, `Secure` in production). The session is replaced on login.
- All input is validated with Pydantic. Templates escape output. Redirect targets are restricted to local paths.
- Ticket codes are random and unguessable (`secrets.token_urlsafe(24)`). Only the ticket owner can load a QR image.
- No secrets in Git. Configuration comes from environment variables.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `ERR_CONNECTION_REFUSED` in the browser | The server is not running. Start `uvicorn app.main:app --reload` and keep that terminal open |
| `ModuleNotFoundError` | Activate the virtual environment and run `pip install -r requirements.txt` |
| Demo accounts say "Invalid email or password" | Set `SEED_DEMO=true` and restart the server |
| Scanner says *outside check-in time* | The event starts more than 2 hours away or has ended. Use an event starting within the next hour |
| Camera does not start | Allow camera access in the browser. On a phone the site must be opened over HTTPS |
| App stops at start-up in production | `SECRET_KEY` is missing. Set it in the host's variables |

---

## Known limitations

- Agents talk over an in-process message bus rather than HTTP inbox endpoints. The timer runs in the web process, so run one worker.
- Venue images are added by URL, not uploaded (hosted disks are not permanent).
- Event times are entered and shown in one local time zone (`TZ_OFFSET_MINUTES`).
- Optional features not implemented: email notifications, time-limited cart holds, advanced search by date or price range.
