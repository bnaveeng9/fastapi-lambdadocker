# fastapi-lambdadocker

## Run the API container locally

Build and start the API with Uvicorn:

```sh
docker compose up --build
```

The API is available directly at <http://localhost:9000>. For example:

```sh
curl http://localhost:9000/
curl http://localhost:9000/health
curl http://localhost:9000/home
curl http://localhost:9000/numbers
curl http://localhost:9000/story/stream/home
```

The root and `/health` endpoints return `{"status":"ok"}`.
The existing REST endpoints remain available, and the MCP Streamable HTTP
endpoint is available at <http://localhost:9000/mcp>.

The `get_otp_messages` MCP tool returns the same recent Gmail inbox messages as
`GET /otp`. Use an MCP client configured to connect to
`http://localhost:9000/mcp`; do not use `/otp` as the MCP URL. Both interfaces
use the same Gmail OAuth configuration described below. This server does not
authenticate callers, so do not expose `/otp` or `/mcp` to untrusted networks
without adding authentication at the application or gateway layer.

Stop the container with Ctrl+C, or run `docker compose down`. The Docker image
runs Uvicorn on port 8080 both locally and in Lambda. The Lambda Web Adapter
extension is inactive outside Lambda.

### Gmail `/otp` authorization in Docker

The container cannot open a browser for Gmail consent. Configure these values
in a root-level `.env` file for Docker Compose, or supply them through your
deployment secret manager:

```dotenv
GOOGLE_CLIENT_ID=your-oauth-client-id
GOOGLE_CLIENT_SECRET=your-oauth-client-secret
GOOGLE_REFRESH_TOKEN=your-google-refresh-token
```

Create the refresh token through Google's OAuth consent flow for the Gmail
read-only scope. The existing local authorization flow can be used to create
the initial saved token; provide its refresh token to the container securely.
Do not commit `.env` files or place credentials in the image. Docker excludes
dotenv files from the build context, while Compose passes the three variables
to the container. The image writes temporary access-token state to `/tmp` and
uses the configured refresh token again when needed.

For Lambda deployments, provide `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`,
and `GOOGLE_REFRESH_TOKEN` as parameters under the deployment workflow's
`/sst/passphrase/fastapi-lambdadocker/` parameter path. `/otp` returns HTTP 503
with setup guidance when the noninteractive OAuth configuration is missing.

## Deploy to AWS Lambda

The GitHub Actions workflow in `.github/workflows/deploy-lambda.yml` runs on
pushes to `main` and can also be started manually. It creates the ECR repository
if it does not exist, builds and pushes an image for the Lambda function's
architecture using Docker Image Manifest V2, Schema 2 with gzip-compressed
layers, verifies the manifest, config, and layer media types in ECR, updates
the existing Lambda function to that image, configures the HTTP API's `$default`
route as a Lambda proxy integration, configures a public Lambda Function URL
with `RESPONSE_STREAM`, and loads
parameters recursively from `/sst/passphrase/fastapi-lambdadocker/` into its
environment. Parameter names relative to that path become environment variable
names; nested path separators are replaced with underscores. For example,
`/sst/passphrase/fastapi-lambdadocker/API_TOKEN` becomes `API_TOKEN`.
The AWS Lambda Web Adapter serves the FastAPI application for both the HTTP API
and Function URL invocations. HTTP API responses remain buffered; the Function
URL enables Lambda response streaming.

Configure GitHub Actions with these variables, either at the repository level
or in each GitHub Environment used for deployment:

- `AWS_REGION`: AWS region containing ECR and the Lambda function.
- `HTTP_API_ID`: ID of the existing API Gateway HTTP API (for example,
  `ajazewyhdg`).
- `ECR_REPOSITORY`: ECR repository name to create or use.
- `LAMBDA_FUNCTION_NAME`: existing Lambda function using the container image
  package type.

Add `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` as repository secrets, or as
secrets in each deployment environment. For environment-scoped secrets, the
workflow uses `production` for pushes to `main` and the selected `dev` or
`production` environment for manual runs. The credentials must belong to a
dedicated IAM user with only the deployment permissions the workflow needs:
`sts:GetCallerIdentity`, `ecr:CreateRepository`,
`ecr:DescribeRepositories`, `ecr:BatchGetImage`, `ecr:GetAuthorizationToken`,
`ecr:BatchCheckLayerAvailability`, `ecr:InitiateLayerUpload`,
`ecr:UploadLayerPart`, `ecr:CompleteLayerUpload`, `ecr:PutImage`,
`ssm:GetParametersByPath`, `lambda:GetFunctionConfiguration`,
`lambda:UpdateFunctionCode`, `lambda:UpdateFunctionConfiguration`,
`lambda:GetFunctionUrlConfig`, `lambda:CreateFunctionUrlConfig`,
`lambda:UpdateFunctionUrlConfig`, `lambda:GetPolicy`, `lambda:AddPermission`,
`apigateway:GET`,
`apigateway:POST`, and `apigateway:PATCH`. Scope permissions to the selected
repository, API, the
`/sst/passphrase/fastapi-lambdadocker/*` SSM parameters, and function where AWS
supports it.

The workflow creates or updates a `$default` Lambda proxy route and ensures the
`$default` stage auto-deploys. That route forwards every request to FastAPI, so
FastAPI handles paths such as `/home`, `/numbers`, and
`/story/stream/home`. The story path returns the same JSON greeting as `/home`.
The root path and `/health` return `{"status":"ok"}`.
Set `HTTP_API_ID` to the API behind the public endpoint, then run the workflow
to apply the route configuration.

The workflow also creates or updates the Lambda Function URL in
`RESPONSE_STREAM` mode and grants anonymous URL invocation (`AuthType=NONE`).
The URL is included in the deployment workflow summary. The Function URL is
public and points to the same Lambda/FastAPI app as the HTTP API, so every app
route is reachable through both URLs; use the HTTP API for ordinary routes and
the Function URL's `/stream` path for incremental output. Choose separate
functions if the Function URL must not expose the normal routes.

## Streaming responses

FastAPI can produce incremental HTTP responses with an ASGI server such as
Uvicorn and `StreamingResponse`. Streaming only reaches the client when every
layer between the application and client forwards chunks without buffering.
The application must also yield data progressively; returning a complete
`Response` (as `/numbers` currently does) is not a streaming response. The new
`/stream` route yields three plain-text chunks with a delay between chunks.
`/story/stream/home` remains an ordinary JSON route, not an SSE endpoint.

### Hosting choices

| Hosting path | Incremental responses? | Use it when |
| --- | --- | --- |
| Uvicorn locally or on a VM | Yes, directly; verify any reverse proxy in front of it. | Development, a small deployment, or full control of the HTTP stack. |
| Docker on a container platform (for example ECS/Fargate, Azure Container Apps, Cloud Run, or Kubernetes) | Generally yes, if the platform ingress/load balancer supports long-lived responses and is configured not to buffer them. | A continuously running ASGI service, predictable streaming, or ordinary container operations. |
| Lambda behind API Gateway HTTP API | No. HTTP API buffers Lambda proxy responses. | Normal JSON/REST endpoints that need API Gateway routing. |
| Lambda Function URL (this deployment's `/stream` path) | Yes, with `RESPONSE_STREAM` and the Lambda Web Adapter. | Incremental response delivery over a direct Lambda URL. |
| Lambda behind API Gateway REST API | Yes, with an `AWS_PROXY` or `HTTP_PROXY` integration configured with response transfer mode `STREAM`, plus a streaming-capable Lambda runtime/adapter. | Streaming with REST API features such as API keys, usage plans, or API Gateway controls. |
| WebSocket service | Bidirectional messages, not a streamed HTTP response. | Interactive two-way communication such as live collaboration; use a WebSocket-capable host and endpoint rather than treating it as SSE. |

The local Uvicorn and container-platform options run FastAPI as a normal ASGI
application. This repository's container starts Uvicorn directly, with the
Lambda Web Adapter translating Lambda events into HTTP requests. The same app
is integrated with the HTTP API for ordinary routes and the Function URL for
streaming. To verify chunk delivery locally:

```sh
curl -N http://localhost:9000/stream
```

For AWS, the image sets `AWS_LWA_INVOKE_MODE=response_stream` and includes the
AWS Lambda Web Adapter. The deployment workflow configures the Function URL
with `InvokeMode=RESPONSE_STREAM`. API Gateway HTTP API remains the entry point
for normal endpoints; HTTP APIs do not support response streaming, so use the
Function URL for `/stream`. Because the Function URL uses `AuthType=NONE`, it
is publicly invokable and exposes every route on the shared FastAPI app.

After deployment, set `FUNCTION_URL` to the base URL printed in the workflow
summary, including its trailing slash, then test incrementality:

```sh
curl -N "${FUNCTION_URL}stream"
```

The three chunks should arrive progressively rather than only after the
connection closes. Lambda Function URL response streaming is unavailable when
the function is in a VPC. Confirm current regional availability and AWS
streaming limits before relying on this design.

AWS streaming also has operational constraints: REST API streams can run for
up to 15 minutes, are subject to endpoint-specific idle timeouts, and responses
larger than the initial unthrottled portion are bandwidth-limited. Lambda
Function URLs also have endpoint-specific idle timeouts. Check current AWS
documentation and regional availability before selecting this design:
[Lambda response streaming](https://docs.aws.amazon.com/lambda/latest/dg/configuration-response-streaming.html),
[API Gateway response streaming](https://docs.aws.amazon.com/apigateway/latest/developerguide/response-transfer-mode.html).

### Proxy, client, and endpoint considerations

- For SSE, return `text/event-stream` and yield correctly framed events
  (`data: ...` followed by a blank line). Send periodic heartbeat comments if
  the connection may otherwise be idle. Use `StreamingResponse` or a suitable
  SSE library; do not build an unbounded in-memory response first.
- For Nginx, disable response buffering for the streaming route (for example,
  `proxy_buffering off`) and set proxy/read timeouts long enough for the
  expected stream. Configure equivalent buffering and idle-timeout settings
  for any ingress, CDN, gateway, or load balancer in the path.
- Test with a streaming-aware client such as `curl -N`; a browser, API client,
  CDN, or application framework may buffer output even when the server emits
  chunks. Verify that events arrive over time, not only after the connection
  closes.
- Choose SSE for one-way server-to-client updates over HTTP. Choose WebSockets
  when the client must send messages on the same live connection. For lengthy
  jobs that do not need a continuously open connection, consider a job ID with
  polling or notifications instead.
- For very large or resumable downloads, object storage with a time-limited
  download URL is often simpler and more scalable than holding an application
  or Lambda invocation open.

Validate incremental delivery through the complete deployed path (including
proxies, timeouts, disconnects, and the actual client) before relying on it in
production.

The Lambda function must already exist, and its execution role and ECR
repository permissions must allow Lambda to retrieve the image. SecureString
parameters are decrypted by the workflow credentials and added to the Lambda
environment; restrict access to both the IAM user and function. If the
parameters use a customer-managed KMS key, also grant the IAM user
`kms:Decrypt` on that key. Prefer short-lived OIDC role credentials when
possible; if using access keys, rotate them regularly and never commit them.
