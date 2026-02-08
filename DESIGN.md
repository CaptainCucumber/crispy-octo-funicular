# Telegram AI Group Chat Bot – Technical Design

## Introduction and Goals

The goal of this project is to implement a **single‑chat Telegram bot** that behaves like a human participant
in a group chat. The bot must

```
read every message in the chat and decide whether it should reply, so it doesn’t spam conversations;
produce responses that mimic the tone and vocabulary of the group (adapt to in‑chat slang, cultural
references, etc.);
run on a small budget (~US $20/month) and remain simple to operate;
be built in Python using modern AI models for language understanding and generation;
support future enhancements such as parsing links posted to the chat and analysing images.
```
The service will target a single Telegram group with low traffic (≈ 100 messages/day). Simplicity, testability
and maintainability are valued over horizontal scalability. This document is written for a junior/mid‑level
engineer and provides architectural guidance, code structure, operational considerations and future
extensions.

## High‑Level Architecture

The bot will run as a container on **Google Cloud Run** , deployed in a free‑tier region to minimise costs.
Instead of polling Telegram for updates, we will expose a **webhook** endpoint and instruct Telegram to push
updates to our service. Telegram’s documentation notes that webhooks avoid the need for polling and
reduce CPU usage because updates are delivered only when messages arrive. Using Cloud Run’s
pay‑as‑you‑go pricing model means the container only accrues CPU and memory charges while handling
requests , and the free tier provides generous allowances – 180 k vCPU‑seconds, 360 k GiB‑seconds and
2 million requests per month. With our low‑volume workload the expected cost is under $1/month for
Cloud Run and Cloud Scheduler , well within the \$20 budget.

To decouple message ingestion from processing and prevent back‑pressure, we introduce a **message
queue** using **Google Cloud Pub/Sub**. The webhook immediately publishes each incoming Telegram update
to a Pub/Sub topic. A separate **message worker** service, also running on Cloud Run with a single instance
and concurrency = 1, subscribes to this topic via a push subscription and processes messages one at a time.
Pub/Sub’s free tier includes **10 GiB of throughput per month** and additional traffic is billed at **\$40 per TiB
after the free 10 GiB**. Message storage costs roughly **\$0.10 – \$0.21 per GiB‑month** with the first
**24 hours free** , and inbound and intra‑region transfers are free. Given our chat volume (~
messages/day), the free tier easily covers all throughput and storage, so adding a queue does not
materially impact the budget.

Persisting conversation history is essential for reproducing context across service restarts and for
generating consistent style metrics. An **in‑memory ring buffer** is fragile because data vanishes when the
container restarts. We therefore use **Cloud Firestore** as a lightweight database to store recent messages

#### • • • • • 1 2 3 4 5

```
6 7
```

and derived style profiles. Firestore’s free tier provides **1 GiB of stored data** , **50 000 reads per day** , **20 
writes per day** , **20 000 deletes per day** , and **10 GiB of outbound data per month**. Only one free
database is allowed per project , but this is sufficient for our single‑chat use case. Storing each message
as a document and updating style statistics will stay well within these quotas.

All secrets (e.g. Telegram bot token, API keys) will be stored in **Google Secret Manager** ; reading a single
secret a few hundred times per month is free. Logging and monitoring will be handled via **Cloud
Logging** and **Cloud Monitoring** , with alerts forwarded to a notification channel.

All secrets (e.g. Telegram bot token, API keys) will be stored in **Google Secret Manager** ; reading a single
secret a few hundred times per month is free. Logging and monitoring will be handled via **Cloud
Logging** and **Cloud Monitoring** , with alerts forwarded to a notification channel.

Below is an updated conceptual diagram of the system. It shows the webhook forwarding updates into a
Pub/Sub queue, a Cloud Run worker consuming messages one‑by‑one, persistent storage in Firestore and
connections to external services. A high‑resolution copy of the diagram is embedded below:

### Key Components

```
Telegram – users send messages in a group chat. Telegram forwards these updates to our bot via a
secure webhook (HTTPS). Webhooks avoid polling overhead and deliver updates immediately.
Cloud Run Services – two services run in Cloud Run’s free tier. The webhook service receives
Telegram updates and publishes them to Pub/Sub. The worker service subscribes to the Pub/Sub
topic and processes messages one by one. Both services configure concurrency = 1 and max
instances = 1 to maintain single‑threaded execution and minimise cost. A single service could
host both roles, but separating them clarifies responsibilities and allows independent scaling.
Webhook Handler – an HTTP endpoint that receives updates from Telegram, validates signatures
and chat id, and immediately publishes the message to a Pub/Sub topic. This decouples ingestion
from processing and prevents spillovers.
```
```
8
9
```
```
10
```
```
10
```
#### 1.

```
1
2.
```
```
2
```
#### 3.


```
Pub/Sub Queue – a managed message bus that stores updates until the worker processes them.
Pub/Sub provides at least‑once delivery semantics and supports push subscriptions so that our
worker receives updates via HTTP. The free tier includes 10 GiB of throughput and 24 hours of free
retention, with additional usage billed per TiB.
Message Worker & Processor – a Cloud Run service triggered by Pub/Sub push. It reads one update
at a time, decides whether to reply, constructs context windows and invokes the AI generation
module. It also persists recent messages and style metrics in Firestore rather than relying on an
in‑memory ring buffer.
AI Adapter – wraps calls to an external AI model (e.g. OpenAI Chat Completion) and ensures
responses match the group’s tone. It can be replaced later with an on‑premise model.
Link Analyzer / Image Analyzer (future) – optional modules that fetch webpages and extract text
using Beautiful Soup, or analyse images using Google Vision API. Their outputs feed into the AI
Adapter to enrich responses.
Persistent Storage (Firestore) – stores conversation history and derived style metrics. Firestore’s
free quota (1 GiB storage, 50 000 reads/day, 20 000 writes/day and 10 GiB outbound data) is
sufficient for our low‑volume chat.
Secret Manager & Config – stores tokens and configuration values; loaded at startup.
Monitoring & Alerting – Cloud Logging exports metrics and Cloud Monitoring triggers alerts on
errors or cost anomalies.
```
## Code Structure and Modules

We recommend organising the Python repository in a standard, testable structure. The key difference from
the earlier design is that we explicitly separate the **webhook publisher** and **queue worker** into their own
modules and favour **synchronous code** over asynchronous constructs. A suggested layout follows:

```
telegram_ai_bot/
│ README.md
│ requirements.txt # pinned dependencies
│ Dockerfile # container build instructions
│ pyproject.toml # poetry or pip build system
│ scripts/deploy.sh # gcloud deployment script
│ scripts/local_tunnel.sh # optional: tunnel webhook during local testing
├─ app/
│ ├─ main.py # Flask entrypoint for the webhook service
(synchronous)
│ ├─ worker.py # Flask entrypoint for the Pub/Sub worker
(synchronous)
│ ├─ config.py # loads environment variables & secrets
│ ├─ webhook_handler.py # receives Telegram updates (POST /telegram/webhook)
and publishes to Pub/Sub
│ ├─ queue_publisher.py # wraps Pub/Sub publish logic
│ ├─ queue_worker.py # validates messages from Pub/Sub and dispatches to
the message processor
│ ├─ message_processor.py # decides whether to respond & builds prompts
│ ├─ ai_adapter.py # wrapper around AI model APIs (synchronous HTTP
```
#### 4.

```
5
5.
```
#### 6.

#### 7.

#### 8.

```
8
9.
10.
```

```
requests)
│ ├─ storage.py # Firestore client and persistence utilities
│ ├─ link_analyzer.py # optional future module to fetch and summarise URLs
│ ├─ image_analyzer.py # optional future module to analyse images
│ ├─ models.py # dataclasses for Update, Message, User, Context
│ ├─ utils.py # helpers (random sampling, text cleaning, logging)
│ ├─ logging_config.py # structured logging setup for Cloud Logging
│ └─ constants.py # threshold values, model parameters etc.
└─ tests/
├─ test_message_processor.py
├─ test_ai_adapter.py
└─ ...
```
Each module has a clear responsibility:

### main.py – Application Entrypoint

The main.py module acts as the entrypoint for the **webhook service** and is intentionally simple and
synchronous. We use **Flask** (or any minimal WSGI framework) rather than FastAPI to avoid asynchronous
complexities. The webhook service exposes the following routes:

```
POST /telegram/webhook: receives raw JSON updates from Telegram. It should immediately
acknowledge with HTTP 200 to avoid timeouts and publish the update to the Pub/Sub topic via
queue_publisher.publish_update. No heavy processing occurs here.
GET /health: a simple health check returning 200/OK. Cloud Run uses this for liveness and
readiness probes.
POST /admin/notify (optional): internal endpoint to send manual notifications.
```
Because there is no concurrency requirement, we deliberately avoid any async def functions or
asynchronous frameworks. Synchronous HTTP handlers are easier to debug and test locally. For local
testing, run flask run rather than an ASGI server.

### config.py – Configuration and Secret Loading

Loads environment variables (e.g. Telegram token, OpenAI API key, project id) and reads secrets from
**Secret Manager**. The script can use the Google Cloud client library to fetch secrets and should cache them
in memory. Failing to load required variables should raise an exception early to avoid misconfiguring the
bot.

### webhook_handler.py – Validating and Dispatching Updates

This module defines a function handle_update(update: dict) -> None which:

```
Parses the incoming update into a structured Update dataclass from models.py.
Discards unsupported update types (e.g. edited messages) until future features are implemented.
```
#### •

#### •

#### •

#### 1.

#### 2.


```
Publishes the update to the configured Pub/Sub topic via
queue_publisher.publish_update(update). Publishing is synchronous; if the publish call fails,
return an HTTP error to Telegram so the message may be retried.
```
Validation includes checking the update.message field and verifying that the message comes from the
configured chat id (to prevent the bot from acting in unintended chats). For security, we compare the
x‑telegram‑bot‑api‑secret‑token header with a shared secret we register when setting the webhook.
The handler does **not** call the message_processor directly—decoupling ingestion and processing
prevents backlog on the webhook.

### queue_worker.py – Consuming from Pub/Sub

The queue_worker.py module runs within the **worker service** and defines a HTTP endpoint (e.g.
POST /pubsub/push) to receive Pub/Sub push subscription payloads. The handler:

```
Verifies the Pub/Sub message signature (JWT) to ensure it originates from Google.
Extracts the original Telegram update from the message data and parses it into an Update
dataclass.
Invokes message_processor.process_update(update) synchronously. All business logic
(deciding whether to reply, constructing prompts, calling the AI adapter, persisting conversation
history) happens in this step.
Acknowledges the Pub/Sub message by returning HTTP 200 when processing succeeds. If
processing raises an exception, return an error so Pub/Sub retries delivery.
```
The worker service configures **concurrency = 1** in Cloud Run so that only one message is processed at a
time. This prevents concurrent AI calls and simplifies state management. Because Pub/Sub guarantees
at‑least‑once delivery, the worker must handle potential duplicates (e.g. by storing processed update ids in
Firestore).

### message_processor.py – Deciding When to Respond

The heart of the bot lies in determining when to respond and constructing the proper prompt for the AI. All
functions in this module are **synchronous** to simplify debugging and local testing. We propose the
following algorithm:

```
Maintain Recent History : retrieve and update a history of the last N (e.g. 50) messages and simple
statistics (authors, words used, topics) from Firestore using functions in storage.py. Keep a small
in‑memory cache to reduce database reads, but persist every new message so that restarts do not
lose context.
Trigger Evaluation : compute a should_reply boolean based on heuristics:
If the message mentions the bot via @botusername, always reply.
If the message contains a question mark or direct second‑person pronouns (“you”) and the bot
hasn’t replied recently.
Random chance (e.g. 10 %) to emulate occasional participation.
Avoid replying to consecutive messages: enforce a cool‑down interval.
Avoid replying to messages sent by itself.
```
#### 3.

#### 1.

#### 2.

#### 3.

#### 4.

#### 1.

#### 2.

#### 3.

#### 4.

#### 5.

#### 6.

#### 7.


```
Topic & Style Extraction : analyse the persisted history to determine prevalent topics and slang.
Compute word frequency, detect trending hashtags or named entities and maintain a simple “style
profile” for the chat (e.g. average message length, use of emojis, formal vs informal tone). The AI
Adapter will use this to guide generation.
Prompt Construction : build a system prompt and user messages for the AI model. The system
prompt defines the bot’s personality (friendly group participant, mimic style, avoid saying it is an AI).
Append a limited subset of recent messages (e.g. last 10) to give the model context. Include
extracted topics and style guidelines.
Call AI Adapter : pass the prompt to ai_adapter.generate_reply(context). The AI call is
synchronous and uses the requests library to invoke the external API. On success, send the
generated text back to Telegram via the synchronous telegram.Bot client.
Persistence & Logging : write the processed update and the bot’s reply to Firestore using
storage.py, and log the decision and outcome (e.g. event id, heuristics triggered, AI latency) to
Cloud Logging. These logs feed Cloud Monitoring metrics.
```
The heuristics can be refined over time. Keep thresholds in constants.py so they can be tuned without
code changes. We deliberately avoid asynchronous methods; although modern versions of
python‑telegram‑bot support async handlers , using synchronous calls makes the execution order
deterministic and easier to test locally. Since the queue enforces single‑threaded processing, latency is
acceptable.

### ai_adapter.py – Interfacing with AI Models

This module isolates all calls to AI services. For the first version we recommend using **OpenAI’s Chat
Completion API** with the gpt‑3.5‑turbo or gpt‑ 4 model, configured with a temperature (e.g. 0.7) to
produce varied replies. Because we avoid asynchronous code, implement a synchronous function:

```
defgenerate_reply(context: AIContext) -> str :
"""Send a prompt to the AI service via an HTTP POST and return the reply
string."""
```
Key considerations:

```
Use the conversation history and style metrics to build the messages list. The system prompt should
instruct the model to answer concisely, mimic the group’s language, avoid revealing it’s a bot, and
keep messages under a certain length (e.g. 3 sentences).
Include user messages with roles ('user', 'assistant') to maintain context. Limit the number
of tokens to stay within API limits.
Use the requests library (or similar) to perform synchronous HTTP requests to the AI provider.
Wrap the call in a try/except block to handle network errors and rate limits gracefully. Do not block
the webhook; the call occurs in the worker process.
When the model returns a reply, post‑process it: remove disallowed content (e.g. explicit or sensitive
language) and ensure it adheres to style guidelines.
Implement fallback logic: if the AI call fails or times out, do not send a reply and log the error;
optionally send a default “I’m busy” message.
Parameterise the model name and API key in config.py.
```
#### 8.

#### 9.

#### 10.

#### 11.

```
11
```
#### • • • • • •


This abstraction allows swapping the AI backend later (e.g. a local LLM on HuggingFace or Google Vertex AI)
without changing the message processor. If an asynchronous backend is introduced in the future, a
separate generate_reply_async function can be added while retaining the synchronous default.

### link_analyzer.py & image_analyzer.py – Future Features

These modules prepare the bot for upcoming capabilities:

```
Link Analyzer : when a message contains a URL, the bot can fetch the web page using requests
and extract readable text with readability-lxml or BeautifulSoup. It can then summarise
the article using the AI Adapter and optionally comment. This should run in a separate asynchronous
task so as not to block the main reply flow. Make sure to respect robots.txt and avoid scraping sites
without permission.
Image Analyzer : when a message includes a photo, the bot can download the image file and call
Google Cloud Vision API to extract labels or text. The AI Adapter can then comment or generate a
caption. For the MVP this will be a stub.
```
### models.py

Define simple dataclasses to represent key objects:

```
@dataclass
classUser:
id : int
username: str
first_name: str
```
```
@dataclass
classMessage:
message_id: int
sender: User
text: str
date: datetime
entities: List[MessageEntity]
```
```
@dataclass
classUpdate:
update_id: int
message: Message
# future: photo, link, etc.
```
```
@dataclass
classAIContext:
chat_id: int
recent_messages: List[Message]
style_profile: StyleProfile
```
#### •

#### •


```
# style metrics may include average sentence length, common words, emoji
frequency, topics.
```
### logging_config.py

Configure Python’s logging module to emit structured JSON logs. Set log level via environment variable (e.g.
INFO for production). Use Cloud Logging’s recommended fields (severity, message, httpRequest
etc.) so that logs appear correctly in the GCP console.

### tests/ – Automated Test Suite

Tests are critical for maintainability. Use pytest to structure tests:

```
test_message_processor.py: mock a series of incoming messages and verify that
should_reply heuristics behave as expected. Use fixtures for sample history and assert the AI
Adapter is called only when conditions hold.
test_ai_adapter.py: mock the OpenAI API using respx or requests_mock to simulate API
responses. Verify that prompts include recent messages and style cues.
test_webhook_handler.py: send fake HTTP POST payloads to the FastAPI test client and ensure
that invalid updates are rejected and valid ones are dispatched correctly.
```
Include tests for failure scenarios (API timeout, malformed updates). Aim for ≥ 90 % coverage.

## Deployment on Google Cloud Run

### Containerisation

Create a Dockerfile with a small base image (e.g. python:3.12-slim). The webhook and worker
services each build from the same image but run different entrypoints. The container should:

```
Copy the application code and install dependencies from requirements.txt using pip --no-
cache-dir to keep the image small.
Expose the Flask application using the built‑in WSGI server or gunicorn for production. Because
we do not use asynchronous code, there is no need for uvicorn.
```
Example Dockerfile:

```
FROMpython:3.12-slim
WORKDIR/app
COPYrequirements.txt ./
RUNpip install--no-cache-dir-r requirements.txt
COPY./app./app
ENVPORT=
# Entrypoint is provided via the Cloud Run service configuration
CMD["gunicorn", "-b", "0.0.0.0:${PORT}", "app.main:app"]
```
#### •

#### •

#### •

#### 1.

#### 2.


### Deployment Script (scripts/deploy.sh)

Use gcloud to build and deploy the container once, then deploy two Cloud Run services from the same
image. You must also create a Pub/Sub topic and push subscription. An example script:

```
#!/bin/bash
set-euopipefail
PROJECT_ID=my-project
REGION=us-west1 # choose a free‑tier region
IMAGE=gcr.io/$PROJECT_ID/telegram-ai-bot
```
```
# Build container
gcloud buildssubmit --tag $IMAGE.
```
```
# Create Pub/Sub topic (idempotent)
gcloud pubsubtopics create telegram-updates || true
```
```
# Create secret environment variables
TG_TOKEN_SECRET="projects/$PROJECT_ID/secrets/telegram-token:latest"
OPENAI_SECRET="projects/$PROJECT_ID/secrets/openai-key:latest"
```
```
# Deploy webhook service
gcloud rundeploy telegram-ai-webhook\
--image$IMAGE \
--platformmanaged\
--region$REGION\
--allow-unauthenticated=false \
--max-instances=1\
--concurrency=1\
--memory=512Mi \
--set-secrets="TG_TOKEN=$TG_TOKEN_SECRET,OPENAI_KEY=$OPENAI_SECRET" \
--set-env-vars="CHAT_ID=123456789,PUBSUB_TOPIC=telegram-updates"\
--entry-pointapp.main:app
```
```
# Deploy worker service
gcloud rundeploy telegram-ai-worker \
--image$IMAGE \
--platformmanaged\
--region$REGION\
--allow-unauthenticated=false \
--max-instances=1\
--concurrency=1\
--memory=512Mi \
--set-secrets="TG_TOKEN=$TG_TOKEN_SECRET,OPENAI_KEY=$OPENAI_SECRET" \
--set-env-vars="CHAT_ID=123456789,PUBSUB_TOPIC=telegram-updates"\
--entry-pointapp.worker:app
```

```
# Create Pub/Sub push subscription pointing at the worker service
WORKER_URL=$(gcloud runservices describe telegram-ai-worker--platform managed
--region$REGION --format'value(status.url)')
gcloud pubsubsubscriptions create telegram-updates-sub\
--topictelegram-updates \
--push-endpoint="$WORKER_URL/pubsub/push"\
--push-auth-service-account="${PROJECT_ID}@appspot.gserviceaccount.com"\
--ack-deadline=600|| true
```
```
echo"Webhook service and worker deployed. Next, register the webhook with
Telegram:"
WEBHOOK_URL=$(gcloud run servicesdescribe telegram-ai-webhook--platform
managed--region $REGION--format'value(status.url)')
curl-X POST"https://api.telegram.org/bot$(gcloud secretsversions access
latest --secrettelegram-token)"/setWebhook\
-d"url=$WEBHOOK_URL/telegram/webhook"\
-d"secret_token=<WEBHOOK_SECRET>"
```
Using a secret token ensures that only Telegram can call the webhook. The requirements for webhooks
(supported ports, TLS and certificates) are explained in Telegram’s official guide. If Cloud Run’s HTTPS
endpoint uses a Google‑managed certificate, no additional setup is needed.

### Cost Considerations

The combination of Cloud Run, Pub/Sub and Firestore keeps monthly costs extremely low:

```
Cloud Scheduler : each job costs about \$0.003 per day, or ~\$0.10 per month, and the first three
jobs per billing account are free. We only use Cloud Scheduler if we decide to schedule
housekeeping tasks (e.g. pruning old Firestore documents) but it is not required for basic operation.
Cloud Run : pricing is based on CPU‑seconds, memory‑seconds and number of requests. Containers
are billed only while processing requests. The free tier provides 180,000 vCPU‑seconds,
360,000 GiB‑seconds and 2 million requests per month , which covers both the webhook and
worker services. Example estimates show that running a Cloud Run function 403 times per month
with 6 s execution and 256 MiB memory costs ~$0.01–0.02 , so our costs stay well below the \$
budget.
Pub/Sub : the first 10 GiB of throughput per month are free. Additional throughput is billed at \$
per TiB. Message storage costs \$0.10–0.21 per GiB‑month , with the first 24 hours free.
Inbound and intra‑region transfers are free. Our chat volume (≈100 messages/day) produces
only a few megabytes of data per month, so Pub/Sub usage remains within the free tier.
Firestore : the free tier includes 1 GiB of stored data , 50 000 reads per day , 20 000 writes per day ,
20 000 deletes per day , and 10 GiB of outbound data transfer per month. Persisting
messages and style profiles for our single chat will remain far below these limits. Once the free
quota is exceeded, reads and writes are billed per operation (on the order of \$0.06 per 100 
reads), which is still inexpensive for our workload.
Secret Manager : storing one secret and reading it a few hundred times per month costs \$.
```
```
12
```
#### •

```
13
```
#### •

```
2
3
```
```
14
```
#### •

```
5 6
7
```
#### •

```
8
```
#### •^10


## Local Development and Testing

### Running Locally

For quick iteration, run the Flask applications directly. Set environment variables and invoke the webhook
service using flask run or the built‑in Werkzeug server. For example:

```
export TG_TOKEN=... # telegram bot token
export OPENAI_KEY=... # AI provider key
export CHAT_ID=
export PUBSUB_TOPIC=telegram-updates
```
```
# Start the webhook service on port 8080
python -m flask--app app.mainrun --port 8080
```
```
# In another terminal, you can simulate Pub/Sub pushes by running the worker
service:
python -m flask--app app.workerrun --port 8081
```
To test the webhook locally without exposing your machine, use **ngrok** or **cloudflare tunnel** :

```
ngrokhttp 8080
```
This yields a public HTTPS URL. Register this URL with the setWebhook API as above. Remember to
include the secret token for security. For Firestore, use the **Firestore Emulator** in the Firebase Emulator
Suite during local development so you do not incur writes against the production database.

### Automated Tests

Use pytest for synchronous unit tests. There are no asynchronous functions, so additional plugins like
pytest‑asyncio are unnecessary. Set up GitHub Actions or Cloud Build triggers to run tests on every
push. Include linting (e.g. flake8, black) and static analysis (e.g. mypy) in the CI pipeline to maintain
code quality. When testing Firestore interactions, use the Firebase Emulator and configure
FIRESTORE_EMULATOR_HOST so tests do not hit production.

Example GitHub Actions workflow:

```
name: CI
on : [push, pull_request]
jobs:
test:
runs-on: ubuntu-latest
steps:
```
- uses: actions/checkout@v


- uses: actions/setup-python@v
    with:
       python-version: '3.12'
- run : pip install -r requirements.txt
- run : pip install pytest
- run : pytest --cov=app

### Debugging

Structured logs appear in Cloud Logging. Use gcloud logs read to stream logs locally or set up an
export to BigQuery for deeper analysis. Add correlation IDs to logs (e.g. update id) to trace a request across
modules.

## Monitoring and Alerting

**Cloud Monitoring** allows us to create alert policies on log entries or metrics. For example:

```
Error Rate Alert – create a logs‑based metric that counts log entries with severity=ERROR.
Configure an alert to notify via email or Slack when errors exceed a threshold (e.g. more than 5
errors in 10 minutes). This allows quick response to exceptions.
Budget Alert – enable Billing Budgets and set a budget of \$20 per month with alerts at 50 %, 80 %
and 100 %. Connect budget alerts to your email so unexpected cost increases are detected.
Latency Alert – record AI response times and create a metric; alert if latency exceeds, say, 5 s. High
latency may indicate issues with the AI provider.
```
To simplify operations, integrate Cloud Monitoring with Chat or Slack for real‑time notifications. Keep the
number of monitored metrics small to avoid complexity.

## Security Considerations

```
Use Secret Manager for all tokens and API keys. Avoid committing secrets to source control.
Validate incoming updates: verify the secret_token header matches what you configured when
setting the webhook. Reject any updates without this header.
Restrict the bot to the intended chat id; ignore messages from other chats. This prevents misuse if
the bot token leaks.
Ensure the container runs with least privilege. Grant only the roles required (Cloud Run Invoker to
the Telegram webhook, Secret Manager Secret Accessor to the service account). Do not allow
unauthenticated access.
Use a free‑tier region (e.g. us-west1) to leverage free credits; network egress within the same
region is free.
```
## Maintenance and Future Work

```
Updating Dependencies – pin dependency versions in requirements.txt and regularly update
them to receive security fixes. Use Dependabot or Renovate to automate dependency updates.
```
#### 1.

#### 2.

#### 3.

#### •

#### •

#### •

#### •

#### •

```
15
```
#### •


```
Refining Heuristics – gather anonymised logs to analyse when the bot replies. Use this data to tune
probabilities and thresholds for reply triggers. Consider training a small ML classifier to predict when
to reply based on features (message length, punctuation, presence of keywords, etc.).
Persistence – conversation history and style profiles are persisted in Cloud Firestore by default. Use
this storage to recover context after restarts. If read/write volumes increase beyond the free tier,
monitor Firestore costs and apply retention policies (e.g. only store the last 30 days of messages).
Cloud Datastore (Firestore in Datastore mode) is another option for very low‑cost document storage.
Link and Image Analysis – gradually implement link_analyzer.py and image_analyzer.py.
For links, use requests and BeautifulSoup to fetch and clean text, then summarise via the AI
Adapter. For images, use the Google Vision API to extract labels or descriptions. Both features should
run asynchronously and only when triggers (e.g. the message contains a URL or has photos) are set.
User Commands – add a few admin commands (e.g. /botstatus, /stats) to inspect the bot’s
state or adjust reply frequency. Use the command handler provided by python-telegram-bot;
the library’s Updater class can dispatch different handlers for commands, messages and callback
queries.
Web UI for Monitoring – optionally build a small dashboard (using Flask/React) to display recent
messages, replies, and metrics. Host it on Cloud Run behind authentication. This is optional but can
help debugging.
```
## Conclusion

This technical design proposes a modular Python application that leverages Google’s serverless offerings to
run a cost‑effective Telegram bot. Updates from Telegram are ingested via a webhook and immediately
placed on a **Pub/Sub queue** , decoupling message ingestion from processing. A **single‑threaded worker**
pulls updates from the queue, persists them to **Firestore** , decides whether to respond and calls an AI model
synchronously. By storing context in Firestore rather than an in‑memory buffer, the bot survives restarts
and simplifies local debugging. The code structure emphasises clear separation of concerns (webhook
publishing, queue consumption, message processing, AI generation) and uses synchronous functions
exclusively for easier testing. Automated tests, continuous integration and monitoring are built into the
plan to ease maintenance. The design also leaves room for future extensions like link summarisation and
image analysis without major restructuring. Following this document should allow a junior or mid‑level
engineer to implement, deploy and operate the Telegram AI buddy successfully within the \$20/month
budget.

Marvin's Marvellous Guide to All Things Webhook
https://core.telegram.org/bots/webhooks

Google Cloud Run Pricing in 2025: A Comprehensive Guide
https://cloudchipr.com/blog/cloud-run-pricing

A Telegram bot for scheduled updates powered by Cloud Run Functions | by Claudio
Rauso | Medium
https://medium.com/@claudiorauso/a-telegram-bot-for-scheduled-updates-powered-by-cloud-run-functions-c6ac631592be

Google Cloud Pub/Sub Pricing Guide: Standard vs. Lite Costs Explained | Airbyte
https://airbyte.com/data-engineering-resources/google-pub-sub-pricing

#### •

#### •

#### •

#### •

```
16
```
-

```
1 12
```
```
2 3 15
```
```
4 10 11 13 14
```
```
5 6 7
```

Usage and limits  |  Firestore  |  Firebase
https://firebase.google.com/docs/firestore/quotas

python-telegram-bot Documentation
https://docs.python-telegram-bot.org/_/downloads/en/v13.13/pdf/

```
8 9
```
```
16
```

