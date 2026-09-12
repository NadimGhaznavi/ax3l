# Haiku experiment

From the checkout root, point the loop at the running model server:

```sh
python3 -m ax3l.app.snakelab.main-loop --url http://HOST:27770
```

The loop sends `Write a haiku.`, saves the response, sleeps five seconds,
and repeats until Ctrl-C. Each request has fresh context. It uses whichever
model is already running on that server. Dev/QA health stubs cannot generate text.

The printed directory under `tmp/haiku/` contains `run.log` (stdout, stderr,
and tracebacks), plus each request JSON, HTTP response headers/status, and exact
response body bytes. Responses are not parsed or filtered. HTTP and transport
errors stop the loop and are recorded in the log.

Use `--count 2` for a short run or `--output /tmp/haiku` to change the output root.
This experiment runs separately from the installed health service.
