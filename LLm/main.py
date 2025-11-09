import json
import os
import sys
from datetime import datetime
from typing import Dict, List, Any, Optional
import requests


class GameEngine:
    def __init__(self, rules_path: str = "rules.json", prompts_dir: str = "prompts"):
        self.rules = self._load_json(rules_path)
        self.gm_prompt = self._load_prompt(f"{prompts_dir}/gm.txt")
        self.state = self.rules["START"].copy()
        self.state["turns"] = 0
        self.history = []
        self.transcript = []
        self.ollama_url = "http://localhost:11434/api/chat"
        self.model = "llama3.1:8b"  # Default model
        
    def _load_json(self, path: str) -> Dict:
        with open(path, 'r') as f:
            return json.load(f)
    
    def _load_prompt(self, path: str) -> str:
        with open(path, 'r') as f:
            return f.read().strip()
    
    def _save_json(self, data: Dict, path: str):
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
    
    def save_game(self, filename: str = "save.json"):
        save_data = {
            "state": self.state,
            "history": self.history[-10:],  # Last 10 turns only
            "timestamp": datetime.now().isoformat()
        }
        self._save_json(save_data, filename)
        print(f"✓ Game saved to {filename}")
    
    def load_game(self, filename: str = "save.json"):
        if not os.path.exists(filename):
            print(f"✗ Save file '{filename}' not found.")
            return False
        save_data = self._load_json(filename)
        self.state = save_data["state"]
        self.history = save_data.get("history", [])
        print(f"✓ Game loaded from {filename}")
        return True
    
    def save_transcript(self, filename: str = "samples/transcript.txt"):
        os.makedirs("samples", exist_ok=True)
        with open(filename, 'w') as f:
            f.write(f"=== AI DUNGEON TRANSCRIPT ===\n")
            f.write(f"Generated: {datetime.now().isoformat()}\n")
            f.write(f"Model: {self.model}\n\n")
            for entry in self.transcript:
                f.write(f"{entry}\n\n")
        print(f"✓ Transcript saved to {filename}")
    
    def check_end_conditions(self) -> Optional[str]:
        """Returns 'WIN', 'LOSE', or None"""
        end = self.rules["END_CONDITIONS"]
        
        # Check max turns
        if self.state["turns"] >= end.get("MAX_TURNS", 999):
            return "LOSE"
        
        # Check lose conditions
        lose_flags = end.get("LOSE_ANY_FLAGS", [])
        for flag in lose_flags:
            if self.state["flags"].get(flag, False):
                return "LOSE"
        
        # Check win conditions
        win_flags = end.get("WIN_ALL_FLAGS", [])
        if win_flags and all(self.state["flags"].get(f, False) for f in win_flags):
            return "WIN"
        
        return None
    
    def enforce_state_change(self, state_change: List[Dict]) -> List[Dict]:
        """Apply rules enforcement and return only legal changes"""
        legal_changes = []
        
        for change in state_change:
            atom_type = change.get("type")
            
            if atom_type == "add_item":
                item = change.get("item")
                if len(self.state["inventory"]) >= self.rules["INVENTORY_LIMIT"]:
                    print(f"  [RULE BLOCKED: Inventory full ({self.rules['INVENTORY_LIMIT']} items max)]")
                    continue
                legal_changes.append(change)
            
            elif atom_type == "remove_item":
                legal_changes.append(change)
            
            elif atom_type == "move_to":
                location = change.get("location")
                locks = self.rules.get("LOCKS", {})
                if location in locks:
                    required_flag = locks[location]
                    if not self.state["flags"].get(required_flag, False):
                        print(f"  [RULE BLOCKED: {location} requires flag '{required_flag}']")
                        continue
                legal_changes.append(change)
            
            elif atom_type == "set_flag":
                legal_changes.append(change)
            
            elif atom_type == "hp_delta":
                legal_changes.append(change)
            
            else:
                print(f"  [UNKNOWN ATOM TYPE: {atom_type}]")
        
        return legal_changes
    
    def apply_state_change(self, state_change: List[Dict]):
        """Apply legal state changes to game state"""
        for change in state_change:
            atom_type = change.get("type")
            
            if atom_type == "add_item":
                item = change["item"]
                if item not in self.state["inventory"]:
                    self.state["inventory"].append(item)
            
            elif atom_type == "remove_item":
                item = change["item"]
                if item in self.state["inventory"]:
                    self.state["inventory"].remove(item)
            
            elif atom_type == "move_to":
                self.state["location"] = change["location"]
            
            elif atom_type == "set_flag":
                flag = change["flag"]
                value = change.get("value", True)
                self.state["flags"][flag] = value
            
            elif atom_type == "hp_delta":
                delta = change["delta"]
                self.state["hp"] = max(0, self.state["hp"] + delta)
                if self.state["hp"] <= 0:
                    self.state["flags"]["hp_zero"] = True
    
    def build_context(self) -> str:
        """Build context for LLM (keep under 2k tokens)"""
        context = f"""CURRENT STATE:
Location: {self.state['location']}
Inventory: {', '.join(self.state['inventory']) if self.state['inventory'] else 'empty'}
HP: {self.state['hp']}
Flags: {', '.join(k for k, v in self.state['flags'].items() if v) if self.state['flags'] else 'none'}
Turn: {self.state['turns']}

RULES:
{json.dumps(self.rules, indent=2)}

RECENT HISTORY (last 3 turns):
"""
        for turn in self.history[-3:]:
            context += f"Player: {turn['input']}\n"
            context += f"GM: {turn['narration'][:200]}...\n\n"
        
        return context
    
    def call_llm(self, player_input: str) -> Optional[Dict]:
        """Call Ollama LLM and return parsed response"""
        context = self.build_context()
        user_message = f"{context}\nPlayer command: {player_input}\n\nRespond with JSON only."
        
        try:
            response = requests.post(
                self.ollama_url,
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": self.gm_prompt},
                        {"role": "user", "content": user_message}
                    ],
                    "stream": False,
                    "options": {"temperature": 0.7}
                },
                timeout=60
            )
            
            if response.status_code != 200:
                print(f"✗ Ollama error: {response.status_code}")
                return None
            
            result = response.json()
            content = result["message"]["content"]
            
            # Try to extract JSON from response
            content = content.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
            
            return json.loads(content)
            
        except requests.exceptions.ConnectionError:
            print("✗ Cannot connect to Ollama. Is it running? (ollama serve)")
            return None
        except json.JSONDecodeError as e:
            print(f"✗ Failed to parse LLM response as JSON: {e}")
            print(f"Response was: {content[:200]}")
            return None
        except Exception as e:
            print(f"✗ LLM call failed: {e}")
            return None
    
    def is_valid_command(self, user_input: str) -> bool:
        """Check if command matches allowed patterns"""
        cmd = user_input.lower().strip()
        
        # Special commands
        if cmd in ["help", "inventory", "save", "load", "quit"]:
            return True
        
        # Check against COMMANDS patterns
        for pattern in self.rules["COMMANDS"]:
            pattern_base = pattern.split()[0]
            if cmd.startswith(pattern_base):
                return True
        
        return False
    
    def show_help(self):
        print("\n=== AVAILABLE COMMANDS ===")
        for cmd in self.rules["COMMANDS"]:
            print(f"  • {cmd}")
        print()
    
    def show_inventory(self):
        if not self.state["inventory"]:
            print("Your inventory is empty.")
        else:
            print(f"Inventory ({len(self.state['inventory'])}/{self.rules['INVENTORY_LIMIT']}):")
            for item in self.state["inventory"]:
                print(f"  • {item}")
    
    def intro(self):
        """Show game introduction"""
        print("\n" + "="*60)
        print("   AI DUNGEON - Rules-Based Adventure")
        print("="*60)
        quest = self.rules["QUEST"]
        print(f"\n📜 QUEST: {quest['name']}")
        print(f"   {quest['intro']}\n")
        print(f"Location: {self.state['location']}")
        print(f"HP: {self.state['hp']} | Inventory: empty")
        print("\nType 'help' for commands, 'quit' to exit.\n")
    
    def game_loop(self):
        """Main game loop"""
        self.intro()
        
        # Initial narration
        initial_response = self.call_llm("look around")
        if initial_response:
            narration = initial_response.get("narration", "You are ready to begin.")
            print(f"🎭 {narration}\n")
        
        while True:
            # Check end conditions
            end_state = self.check_end_conditions()
            if end_state == "WIN":
                print("\n" + "="*60)
                print("🎉 VICTORY! You have completed the quest!")
                print("="*60)
                break
            elif end_state == "LOSE":
                print("\n" + "="*60)
                print("💀 GAME OVER!")
                print("="*60)
                break
            
            # Get player input
            try:
                user_input = input("▶ ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nQuitting...")
                break
            
            if not user_input:
                continue
            
            # Handle special commands
            if user_input.lower() == "quit":
                print("Thanks for playing!")
                break
            
            if user_input.lower() == "help":
                self.show_help()
                continue
            
            if user_input.lower() == "inventory":
                self.show_inventory()
                continue
            
            if user_input.lower() == "save":
                self.save_game()
                continue
            
            if user_input.lower() == "load":
                if self.load_game():
                    print(f"Location: {self.state['location']} | HP: {self.state['hp']}")
                continue
            
            # Validate command
            if not self.is_valid_command(user_input):
                print(f"✗ Unknown command. Type 'help' for valid commands.")
                continue
            
            # Call LLM
            response = self.call_llm(user_input)
            if not response:
                print("✗ Failed to get response from Game Master. Try again.")
                continue
            
            # Extract response
            narration = response.get("narration", "...")
            state_change = response.get("state_change", [])
            
            # Enforce rules
            legal_changes = self.enforce_state_change(state_change)
            
            # Apply changes
            self.apply_state_change(legal_changes)
            
            # Increment turn
            self.state["turns"] += 1
            
            # Record history
            self.history.append({
                "turn": self.state["turns"],
                "input": user_input,
                "narration": narration,
                "state_change": legal_changes
            })
            
            # Record transcript
            self.transcript.append(f"[Turn {self.state['turns']}]")
            self.transcript.append(f"Player: {user_input}")
            self.transcript.append(f"GM: {narration}")
            self.transcript.append(f"State: {json.dumps(legal_changes)}")
            
            # Display narration
            print(f"\n🎭 {narration}")
            
            # Show status
            status_parts = [f"HP: {self.state['hp']}"]
            if self.state["inventory"]:
                status_parts.append(f"Items: {len(self.state['inventory'])}")
            print(f"   [{' | '.join(status_parts)}]\n")
        
        # Save transcript on exit
        if self.transcript:
            self.save_transcript()


def main():
    """Entry point"""
    if len(sys.argv) > 1:
        model = sys.argv[1]
        print(f"Using model: {model}")
    else:
        model = "llama3.1:8b"
    
    engine = GameEngine()
    engine.model = model
    
    try:
        engine.game_loop()
    except Exception as e:
        print(f"\n✗ Fatal error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()