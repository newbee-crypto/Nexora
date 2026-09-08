# 🛰️ Nexora — The AI Copilot Powering Modern CRM & Campaigns

Nexora hands Indian e-commerce teams a conversational control panel for their entire marketing lifecycle. Instead of clicking through dashboards, marketers simply *talk* to the system — describing who they want to reach, and Nexora handles segmentation, channel selection, copywriting, dispatch, and live funnel reporting (with ROI baked in) from a single chat window.

## 🏗️ How It's Put Together

Nexora runs as a set of loosely coupled services: a Next.js interface up front, a FastAPI service handling business logic, PostgreSQL for persistence, and a stand-in delivery provider that simulates real-world message sending.

### Data Flow at a Glance

```mermaid
graph TD
    %% Frontend Block
    subgraph Frontend [Next.js 14 App Router - Fully Responsive]
        UI[CRM Dashboard & Analytics]
        Chat[AI Copilot Chat UI & Responsive Mobile Slider]
    end

    %% Backend Block
    subgraph Backend [FastAPI CRM Backend — Port 8000]
        Router[Router Layer /campaigns, /customers, /chat]
        Copilot[Copilot Coordinator /agent]
        Rotator[Gemini API Key Rotator Pool]
        Dispatcher[Campaign Dispatcher /dispatcher]
        Receipts[Receipt Webhook /receipts]
        PriorityMap[Webhook Status Priority Guard]
    end

    %% Database Block
    subgraph Storage [PostgreSQL 15]
        DB[(PostgreSQL Database)]
    end

    %% Channel Simulator Block
    subgraph Simulator [Channel Stub Service — Port 8001]
        StubAPI[Simulator API /send]
        Engine[Delivery Simulation Engine]
    end

    %% External LLM API
    LLM[Gemini API Rotation Pool]

    %% Data Flow Connections
    UI <-->|HTTP REST / stats polling| Router
    Chat <-->|HTTP POST /chat| Router
    Router <-->|Session Store & Copilot Context| Copilot
    Copilot <-->|Function Calling / Text Generation| LLM
    Copilot -- 429 Too Many Requests --> Rotator
    Copilot -->|Parse Goal| Dispatcher
    Dispatcher -->|1. Bulk Create Communications| DB
    Dispatcher -->|2. POST Async Messages| StubAPI
    StubAPI -->|202 Accepted & Spawn Task| Engine
    Engine -->|Wait Delays & Roll Dice| Engine
    Engine -->|3. POST Event Receipt| Receipts
    Receipts -->|4. Priority Map Guard| PriorityMap
    PriorityMap -->|5. Atomic Transaction: Update Status & Logs| DB
```

---

## ⚡ What It Can Do

1. **Talk-to-Segment Copilot** — Describe a goal in plain English or Hinglish ("*Send a free gift to customers who bought more than 3 times*") and the copilot uses LLM function calling to translate that into real filters, pull matching orders, suggest a channel, and draft copy.
2. **Rotating Gemini Key Pool** — Gemini's free tier caps out at 20 requests/minute, so Nexora cycles across 5 API keys whenever it hits a 429, stretching available quota.
3. **Hinglish Pronoun Memory** — References like *"unko"*, *"inhe"*, *"inko"*, or *"yeh log"* automatically resolve to whatever audience was just discussed, skipping a redundant round-trip to the LLM.
4. **Mobile-First Layouts** — Panels reflow and swap dynamically on smaller screens, directories collapse, and nothing scrolls sideways.
5. **Non-Blocking Dispatch** — Background thread workers and asyncio semaphores push messages out to the provider in batches without freezing the request cycle.
6. **Live Funnel Tracking** — Every recipient's journey (`Queued → Sent → Delivered → Opened → Clicked → Purchased`) updates in real time, protected by atomic status-priority checks in Postgres.
7. **Built-In ROI Math** — Per-message costs (WhatsApp ₹0.80, SMS ₹0.20, Email ₹0.05) are tracked automatically and matched against order data to surface real campaign revenue.
8. **Retargeting Suggestions** — The copilot flags cold leads on its own ("*I found 120 customers who received WhatsApp but did not open. Send SMS instead?*") and can spin up the follow-up segment immediately.
9. **Memory Across Turns** — Filters and campaign details (discounts, offers, sale terms) carry forward through multi-turn edits instead of being wiped out by a short follow-up correction.
10. **RFM-Aware Recommendations** — Ask the copilot to read the CRM data and sort customers into RFM tiers (Champions, Loyal, Promising, About to Sleep, At Risk, Hibernating), then suggest campaigns targeted at each.
11. **Number-Word Normalization** — Spelled-out numbers ("*one*", "*two*") get converted to digits before matching runs, keeping segment logic deterministic and rate-limit-safe.

---

## ⚙️ Engineering Choices Behind the Scenes

A few deliberate trade-offs shaped how this was built — worth knowing going in:

### Background Jobs Instead of Celery

Dispatch runs on FastAPI's built-in `BackgroundTasks` rather than Celery. Celery would mean standing up Redis or RabbitMQ — extra infrastructure that isn't justified below ~50,000 customers, where the event loop and thread workers already keep up comfortably. Scaling into the millions would call for a real Celery setup with per-provider queues, rate limiting, and dead-letter retries.

### Guarding Against Out-of-Order Webhooks

Delivery callbacks don't always arrive in sequence — an `opened` event can beat a `delivered` event to the server. Left unguarded, that would let a late `delivered` callback stomp on a more advanced `opened` status. The fix is a `STATUS_PRIORITY` ranking (`{"queued": 0, "sent": 1, "failed": 2, "delivered": 3, "opened": 4, "clicked": 5, "purchased": 6}`), and updates only apply when the incoming status outranks the current one.

### Denormalizing for Speed

Fields like `total_orders`, `total_spent`, `first_order_date`, and `last_order_date` live directly on the `Customer` row rather than being computed on the fly. That means a segment query like "inactive 45+ days and spent over ₹5,000" resolves instantly, with no expensive joins across millions of order rows — the aggregates just get updated atomically whenever an order closes.

### Working Around Gemini's Rate Ceiling

Google's free tier tops out at 20 requests per minute, which a naive tool-calling loop (four sequential calls) would burn through on a single message. Instead, filter parsing, channel suggestions, and preview building all happen deterministically in Python and SQL — the LLM only gets called once per turn, purely for copy generation.

### Keeping Multi-Turn Edits Honest

Corrections mid-conversation used to wipe out unrelated filters or overwrite carefully written campaign copy. A memory layer now pulls forward the last set of filters and merges in new ones, with a noise-stripping step (`clean_copywriting_noise`) to stop promo phrases like "buy 2 get 3" from being misread as a filter value. Clear reset phrases ("*anything*", "*no limit*") are recognized and handed to the LLM to null out the relevant slot.

---

## 🚀 Getting It Running Locally

### What You'll Need

- Docker Desktop (runs PostgreSQL)
- Python 3.10+
- Node.js 18+

### Step 1 — Spin Up the Database

```bash
docker-compose up -d
```

### Step 2 — Set Up the CRM Backend

1. Move into the backend directory:
   ```bash
   cd backend
   ```
2. Create and enter a virtual environment:
   ```bash
   python -m venv venv
   # Windows (PowerShell)
   .\venv\Scripts\Activate.ps1
   # macOS/Linux
   source venv/bin/activate
   ```
3. Install the required packages:
   ```bash
   pip install -r requirements.txt
   ```
4. Duplicate `.env.example` as `.env` and fill in your credentials:

   ```env
   DATABASE_URL=postgresql://postgres:postgres@localhost:5432/xeno_crm

   # Rotation keys for Gemini API
   GEMINI_KEY_1=your_first_gemini_api_key_here
   GEMINI_KEY_2=your_second_gemini_api_key_here
   GEMINI_KEY_3=your_third_gemini_api_key_here
   GEMINI_KEY_4=your_fourth_gemini_api_key_here
   GEMINI_KEY_5=your_fifth_gemini_api_key_here

   OPENAI_BASE_URL=https://generativetool.googleapis.com/v1beta/openai/
   OPENAI_MODEL=gemini-2.5-flash
   ```

5. Populate the database with 400 sample Indian customer profiles:
   ```bash
   python seed.py
   ```
6. Launch the API server:
   ```bash
   python -m uvicorn main:app --host 127.0.0.1 --port 8000
   ```

### Step 3 — Bring Up the Channel Simulator

1. Switch to the stub service folder:
   ```bash
   cd ../channel-stub
   ```
2. Create and activate its virtual environment:
   ```bash
   python -m venv venv
   # Windows (PowerShell)
   .\venv\Scripts\Activate.ps1
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Copy over the environment file:
   ```env
   CRM_RECEIPT_URL=http://localhost:8000
   ```
5. Start the simulator:
   ```bash
   python -m uvicorn main:app --host 127.0.0.1 --port 8001
   ```

### Step 4 — Start the Frontend

1. Head into the frontend directory:
   ```bash
   cd ../frontend
   ```
2. Install packages:
   ```bash
   npm install
   ```
3. Set the API URL:
   ```env
   NEXT_PUBLIC_API_URL=http://localhost:8000
   ```
4. Run the dev server:
   ```bash
   npm run dev
   ```
5. Visit `http://localhost:3000` to try it out.

---

## 🎯 Checking Everything Works End-to-End

Walk through this sequence to confirm the whole pipeline behaves correctly:

1. **Build a campaign in chat**: Go to `/chat` and enter something like `"Target customers with avg spend > 5000 and total orders >= 3"`.
2. **Check the draft**: Confirm the preview shows audience size, a suggested channel, drafted messages, and an **Estimated Campaign Cost**.
3. **Send it**: Hit `Launch Campaign`.
4. **Watch the funnel**: Open the live funnel view and click the **Deliver**, **Open**, **Click**, and **Purchase** buttons to confirm counts, ROI recovery numbers, and the SVG timeline all update live.