.PHONY: start stop status

start:
	open -a Ollama
	sleep 2
	docker compose up -d
	uv run larvis status

stop:
	docker compose down
	osascript -e 'quit app "Ollama"'
	@echo "Larvis stopped."

status:
	uv run larvis status
