`qwenv-tools.jinja` combines the Qwen2.5 tool-call format with Qwen2.5-VL's
image/video markers. It is selected explicitly by the QwenV service.

Sources:
- https://github.com/ggml-org/llama.cpp/blob/master/models/templates/Qwen-Qwen2.5-7B-Instruct.jinja
- https://huggingface.co/Qwen/Qwen2.5-VL-3B-Instruct/blob/main/tokenizer_config.json

Keep image markers and tool-call delimiters intact: llama-server uses them to
process vision inputs and recognize structured tool calls.
