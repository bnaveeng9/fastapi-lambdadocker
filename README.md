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

Stop the container with Ctrl+C, or run `docker compose down`. The Docker image
retains its Lambda handler command for AWS deployments; Compose overrides it
locally to run Uvicorn.

## Deploy to AWS Lambda

The GitHub Actions workflow in `.github/workflows/deploy-lambda.yml` runs on
pushes to `main` and can also be started manually. It creates the ECR repository
if it does not exist, builds and pushes an image for the Lambda function's
architecture using Docker Image Manifest V2, Schema 2 with gzip-compressed
layers, verifies the manifest, config, and layer media types in ECR, updates
the existing Lambda function to that image, configures the HTTP API's `$default`
route as a Lambda proxy integration, and loads
parameters recursively from `/sst/passphrase/fastapi-lambdadocker/` into its
environment. Parameter names relative to that path become environment variable
names; nested path separators are replaced with underscores. For example,
`/sst/passphrase/fastapi-lambdadocker/API_TOKEN` becomes `API_TOKEN`.
The workflow also sets the Lambda image command to
`fastapi_lambdadocker.handler`, uses the Lambda function ARN for the HTTP API
integration, and grants invocation permission for the `$default` route.

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
`lambda:GetPolicy`, `lambda:AddPermission`, `apigateway:GET`,
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

## Streaming responses

FastAPI can produce incremental HTTP responses with an ASGI server such as
Uvicorn and `StreamingResponse`. Streaming only reaches the client when every
layer between the application and client forwards chunks without buffering.
The application must also yield data progressively; returning a complete
`Response` (as `/numbers` currently does) is not a streaming response. The
`/story/stream/home` route currently returns ordinary JSON and is not an SSE
endpoint.

### Hosting choices

| Hosting path | Incremental responses? | Use it when |
| --- | --- | --- |
| Uvicorn locally or on a VM | Yes, directly; verify any reverse proxy in front of it. | Development, a small deployment, or full control of the HTTP stack. |
| Docker on a container platform (for example ECS/Fargate, Azure Container Apps, Cloud Run, or Kubernetes) | Generally yes, if the platform ingress/load balancer supports long-lived responses and is configured not to buffer them. | A continuously running ASGI service, predictable streaming, or ordinary container operations. |
| Lambda behind API Gateway HTTP API (the current deployment) | No. The current Mangum + HTTP API proxy path returns a buffered response. | Short request/response APIs where server-side streaming is not required. |
| Lambda Function URL | Yes, with response streaming enabled and a compatible runtime/adapter. | A simpler AWS HTTP endpoint where API Gateway's additional routing and authorization features are not needed. |
| Lambda behind API Gateway REST API | Yes, with an `AWS_PROXY` or `HTTP_PROXY` integration configured with response transfer mode `STREAM`, plus a streaming-capable Lambda runtime/adapter. | Streaming with REST API features such as API keys, usage plans, or API Gateway controls. |
| WebSocket service | Bidirectional messages, not a streamed HTTP response. | Interactive two-way communication such as live collaboration; use a WebSocket-capable host and endpoint rather than treating it as SSE. |

The first two paths run FastAPI as a normal ASGI application. This repository's
Docker image currently starts the Lambda handler by default; the Compose
configuration overrides that command to start Uvicorn for local HTTP hosting.
For a non-Lambda container deployment, configure its command to run Uvicorn,
for example:

```sh
uvicorn fastapi_lambdadocker:app --host 0.0.0.0 --port 8080
```

For AWS Lambda, deploying a `StreamingResponse` alone is not sufficient:
Mangum's standard API Gateway HTTP API integration and the HTTP API response
path used by this workflow are buffered. Lambda response streaming needs a
compatible runtime/adapter (for example, AWS Lambda Web Adapter) as well as a
streaming-capable invocation path. For a Function URL, enable response
streaming (`RESPONSE_STREAM`) and configure the adapter/runtime accordingly.
For API Gateway, use a REST API proxy integration and set its response transfer
mode to `STREAM`; HTTP APIs do not support response streaming. These are
different architectures and are not configured by this repository's workflow.

AWS streaming also has operational constraints: REST API streams can run for
up to 15 minutes, are subject to endpoint-specific idle timeouts, and responses
larger than the initial unthrottled portion are bandwidth-limited. Lambda
Function URLs do not support response streaming when the function is in a VPC.
Check the current AWS documentation and regional availability before selecting
this design:
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

No streaming endpoint is currently implemented in this sample. Add and test
the FastAPI streaming route separately, then validate incremental delivery
through the complete deployed path (including proxies, timeouts, disconnects,
and the actual client) before relying on it in production.

The Lambda function must already exist, and its execution role and ECR
repository permissions must allow Lambda to retrieve the image. SecureString
parameters are decrypted by the workflow credentials and added to the Lambda
environment; restrict access to both the IAM user and function. If the
parameters use a customer-managed KMS key, also grant the IAM user
`kms:Decrypt` on that key. Prefer short-lived OIDC role credentials when
possible; if using access keys, rotate them regularly and never commit them.
