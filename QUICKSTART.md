=== SYMBIONT — ЗАПУСК ===

1. Termux → сеанс 1 (мозг):

cd ~/llama.cpp
./build/bin/llama-server -m ~/models/qwen2.5-1.5b-instruct-q4_k_m.gguf --port 11434

Ждёшь: listening on http://127.0.0.1:11434
Не закрываешь.

2. Termux → свайп влево → New session (Symbiont):

cd ~/symbiont
python core/symbiont_core.py

3. В Symbiont:

llm on http://localhost:11434 qwen2.5
proactive on
listen on

4. Termux → ещё один сеанс (защита):

termux-wake-lock

5. Телефон на зарядку. Не закрывать Termux.

=== ПРОВЕРКА ===

say привет
proactive now
speak Привет из Symbiont
memory
exit

=== ЕСЛИ ЧТО-ТО НЕ ТАК ===

cd: no such file → папки нет
llama-server: not found → мозг не собран
LLM недоступен → мозг не запущен
