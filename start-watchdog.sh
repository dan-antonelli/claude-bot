#!/bin/bash
SESSION="claude-watchdog"
if tmux has-session -t $SESSION 2>/dev/null; then
    echo "Watchdog already running."
    echo "Attach:  tmux attach -t $SESSION"
    echo "Detach:  Ctrl+B then D"
else
    tmux new-session -d -s $SESSION
    tmux send-keys -t $SESSION "python3 $(dirname "$0")/watchdog.py" Enter
    echo "Watchdog started in tmux session '$SESSION'."
    echo "Attach:  tmux attach -t $SESSION"
    echo "Detach:  Ctrl+B then D"
    echo "Kill:    tmux kill-session -t $SESSION"
fi
