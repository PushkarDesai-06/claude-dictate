## Summary

We are trying to make a claude code wrapper where we use the /voice mode from claude code to transcribe live speech to perform speech to text and paste or type it in the application which is currently focused.

## Steps

Part 1 — Validate Claude Code as a standalone transcription engine
Goal: Get Claude Code's voice dictation working inside a dedicated PTY session and prove that we can control it programmatically.

We won't touch Hyprland global shortcuts or clipboard injection yet. First, we need a reliable transcription foundation.
Phase 1. Environment setup
Objective: Prepare an isolated Claude Code terminal.

Install dependencies:
sudo pacman -S kitty tmux jq ydotool

Verify Claude Code:
claude --version

Requirements:

- Claude Code v2.1.69 or newer.
- Authenticated using your Claude.ai account.
- Working microphone.
- Kitty and tmux installed.
  Deliverable: A persistent tmux session running Claude Code.
  Phase 2. Enable voice dictation
  Objective: Verify that Claude's transcription works independently.

1. Launch the dedicated session:
   ~/.local/bin/claude-dictate-start

2. Inside Claude Code, execute:
   /voice

3. Test the default push-to-talk interaction:
   - Hold Space.
   - Speak a sentence.
   - Release Space.
   - Verify the transcript appears in the input editor.
4. Confirm that the text isn't submitted automatically.
   Deliverable: Working voice transcription.
   Phase 3. Configure deterministic keybindings
   Objective: Replace the default Space interaction with a dedicated modifier combination.

Configure ~/.claude/keybindings.json:
{
"bindings": [
{
"context": "Chat",
"bindings": {
"ctrl+shift+space": "voice:pushToTalk"
}
}
]
}

Restart Claude Code and test:
Action Expected result
Hold Ctrl+Shift+Space Recording starts
Continue holding Recording continues
Release combination Recording stops
Wait Transcript appears

The exact keybinding behavior must be verified against your Claude Code version.
Phase 4. Investigate PTY interaction
Objective: Understand how to control Claude Code externally.

We'll investigate four things.

A. Session management
tmux list-sessions

B. Terminal input
tmux send-keys -t claude-dictate C-c

We'll test synthetic input carefully, without accidentally submitting prompts.

C. Terminal output
tmux capture-pane -t claude-dictate -p

Determine:

- Where the transcript appears.
- Whether partial transcription is visible.
- Whether finalized text remains in the input editor.
- Whether the terminal buffer contains enough information to recover it.
  D. Key event delivery

Test ydotool key-down/key-up events and determine whether Claude Code receives them correctly.
Phase 5. Build the transcript extractor
Objective: Extract dictated text without submitting it.

Potential approaches:

1. Read the terminal's rendered input buffer.
2. Use terminal escape sequences or accessibility information if available.
3. Investigate whether Claude Code exposes a more stable input-state interface.
   We should not assume that tmux capture-pane gives us the raw prompt. Claude Code uses a full-screen TUI, so the visible buffer may contain borders, cursor positioning, and other rendering artifacts.

Deliverable: A Python function:
def get_transcript() -> str: ...

It should return only the dictated text.
