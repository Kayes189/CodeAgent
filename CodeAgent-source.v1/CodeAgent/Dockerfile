# Headless (CLI) image. The Tkinter GUI is a Windows desktop feature and is
# not available in this container; use `run` / `preprocess` subcommands.
FROM python:3.12-slim

WORKDIR /app
COPY codeagent ./codeagent
COPY main.py requirements.txt ./

# No runtime dependencies to install (stdlib only); keep pip available for tests.
RUN pip install --no-cache-dir pytest

# API settings are provided via environment variables:
#   CODEAGENT_API_KEY, CODEAGENT_BASE_URL, CODEAGENT_MODEL
# Mount inputs and outputs, e.g.:
#   docker run --rm -e CODEAGENT_API_KEY=sk-... \
#     -v %cd%\inputs:/data -v %cd%\output:/out codeagent \
#     run --doc /data/Architecture_Documentation.md \
#         --view /data/Architecture_View.md --out /out
ENTRYPOINT ["python", "main.py"]
CMD ["--help"]
