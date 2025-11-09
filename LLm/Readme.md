# AI Dungeon - Local LLM Text Adventure

A rules-based text adventure game powered by a local LLM (Ollama). The game enforces strict rules defined in JSON while using an AI Game Master for dynamic narration.

## Features

- 🎮 **Rule-Based Engine**: Game logic enforced by Python, not by the LLM
- 🤖 **Local AI GM**: Uses Ollama for dynamic, contextual narration
- 🔐 **Lock System**: Locations require flags/items to access
- 📦 **Inventory Management**: Hard limit enforcement
- 💾 **Save/Load**: Persistent game state
- 📝 **Transcript Logging**: Every session saved for review
- ✅ **Win/Lose Conditions**: Clear end goals

## Installation

### 1. Install Ollama

Download and install Ollama from [ollama.ai](https://ollama.ai)

```bash
# Linux/Mac
curl -fsSL https://ollama.ai/install.sh | sh

# Or download from website for Windows/Mac
```

### 2. Pull a Model

```bash
# Recommended: Fast and capable
ollama pull llama3.1:8b

# Alternative options:
ollama pull mistral:7b
ollama pull gemma2:9b
ollama pull qwen2.5:7b
```

### 3. Start Ollama Server

```bash
ollama serve
```

Keep this running in a separate terminal.

### 4. Setup Python Environment

```bash
# Create project directory
mkdir ai-dungeon
cd ai-dungeon

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install requests

# Place all project files in this directory
```

### 5. Create Directory Structure

```
ai-dungeon/
├── main.py
├── rules.json
├── prompts/
│   └── gm.txt
├── samples/
│   └── transcript.txt (auto-generated)
└── README.md
```

## Usage

### Start a New Game

```bash
python main.py
```

### Use a Different Model

```bash
python main.py mistral:7b
```

### Available Commands

In-game, type `help` to see all commands:

- `look` - Examine surroundings
- `move <place>` - Travel to a location
- `take <item>` - Pick up an item
- `use <item>` - Use an item
- `talk <npc>` - Speak with NPCs
- `inventory` - Check your items
- `save` - Save current game
- `load` - Load saved game
- `quit` - Exit game

## How Rules Work

### rules.json Structure

```json
{
  "COMMANDS": ["look", "move <place>", ...],
  "INVENTORY_LIMIT": 5,
  "LOCKS": {
    "Ancient Gate": "have_golden_key"
  },
  "QUEST": {
    "name": "Quest Title",
    "goal_flag": "quest_complete",
    "intro": "Quest description"
  },
  "END_CONDITIONS": {
    "WIN_ALL_FLAGS": ["crown_recovered", "returned_to_village"],
    "LOSE_ANY_FLAGS": ["hp_zero"],
    "MAX_TURNS": 50
  }
}
```

### Rule Enforcement

The engine enforces rules **after** the LLM responds:

1. **Command Validation**: Only listed commands accepted
2. **Inventory Limit**: Blocks `add_item` if inventory is full
3. **Location Locks**: Blocks `move_to` if required flag is missing
4. **HP Tracking**: Sets `hp_zero` flag when HP ≤ 0
5. **Turn Limit**: Triggers LOSE condition at MAX_TURNS

### Adding Custom Content

#### Add a New Location

1. Add to `LOCKS` if it requires a flag:
```json
"LOCKS": {
  "Secret Room": "solved_puzzle"
}
```

2. Add description to `WORLD_DESCRIPTION`:
```json
"Secret Room": "A hidden chamber filled with treasure."
```

#### Add a New Item

Add to `ITEMS` section:
```json
"magic_sword": "A legendary blade that glows blue"
```

#### Modify the Quest

Change the `QUEST` section:
```json
"QUEST": {
  "name": "Slay the Dragon",
  "goal_flag": "dragon_defeated",
  "intro": "A dragon terrorizes the land..."
}
```

Then update `WIN_ALL_FLAGS` in `END_CONDITIONS`.

## Example Game Session

### Starting the Game

```
=== AI DUNGEON - Rules-Based Adventure ===

📜 QUEST: Recover the Stolen Crown
   The village elder begs you to recover the Crown of Light...

Location: Village Square
HP: 10 | Inventory: empty

🎭 You stand in the bustling Village Square. The Elder's house 
   stands to the north, and you can see a path leading west 
   toward mysterious ruins.

▶ look
```

### Trying a Locked Location

```
▶ move Ancient Gate

[RULE BLOCKED: Ancient Gate requires flag 'have_golden_key']

🎭 You approach the massive Ancient Gate, but it's sealed with 
   mystical runes. You'll need the golden key to pass through.
```

### Reaching Inventory Limit

```
▶ take ancient_scroll

[RULE BLOCKED: Inventory full (5 items max)]

🎭 Your backpack is completely full. You'll need to drop 
   something before taking more items.
```

### Winning the Game

```
▶ use crown on pedestal

🎭 You place the Crown of Light back in its rightful place. 
   Brilliant golden light floods the village, ending the 
   darkness forever!

====================================
🎉 VICTORY! You have completed the quest!
====================================

✓ Transcript saved to samples/transcript.txt
```

## State Change Atoms

The LLM can emit these state change atoms:

```json
{"type": "add_item", "item": "torch"}
{"type": "remove_item", "item": "rope"}
{"type": "move_to", "location": "Forest Path"}
{"type": "set_flag", "flag": "door_unlocked", "value": true}
{"type": "hp_delta", "delta": -3}
```

The engine validates and applies only legal changes.

## Troubleshooting

### "Cannot connect to Ollama"

- Make sure `ollama serve` is running
- Check if port 11434 is available
- Try: `curl http://localhost:11434/api/tags`

### "Failed to parse LLM response as JSON"

- Some models struggle with JSON formatting
- Try a different model (llama3.1 is most reliable)
- The engine attempts to extract JSON from markdown blocks

### Model is too slow

- Use smaller models: `mistral:7b` or `gemma2:9b`
- Reduce context by modifying `build_context()` in main.py
- Consider quantized models: `llama3.1:8b-q4_0`

### Rules not being enforced

- Check `rules.json` for syntax errors
- Review transcript to see what state_change atoms are emitted
- The engine logs `[RULE BLOCKED]` messages for violations


## Architecture

```
┌─────────────┐
│   Player    │
└──────┬──────┘
       │ Input
       ▼
┌─────────────────────┐
│   Game Engine       │
│  (main.py)          │
│  • Validate command │
│  • Build context    │
│  • Call LLM         │
│  • Enforce rules    │
│  • Update state     │
│  • Check end        │
└──────┬──────────────┘
       │ Context + Rules
       ▼
┌─────────────────────┐
│   Ollama LLM        │
│  (Local Model)      │
│  • Generate story   │
│  • Emit atoms       │
└──────┬──────────────┘
       │ JSON Response
       ▼
┌─────────────────────┐
│   Rule Enforcer     │
│  • Block illegal    │
│  • Apply legal      │
│  • Update flags     │
└─────────────────────┘
```