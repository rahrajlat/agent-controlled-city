"""Agent City - run with:  uv run python main.py

A miniature city. You create incidents (fire, theft, flood); a Strands agent decides which of the
limited emergency units to send where. Everything is shown live in the terminal (Textual).

  n  new incident   r  random incident   x  crisis (many at once)   p  switch planner (agent / rules)
  i  agent info (what the agent sees, its tools, what it has done)
  space pause   1/2/3 speed   q quit

  --rules        use the deterministic rule planner instead of the agent
  --model NAME   Ollama model for the agent (default: gpt-oss:120b-cloud, or $AGENT_CITY_MODEL)
"""

import argparse

from tui.app import run

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rules", action="store_true", help="use the rule planner instead of the Strands agent")
    parser.add_argument("--model", default=None, help="Ollama model id for the agent")
    args = parser.parse_args()
    run(planner="rules" if args.rules else "agent", model=args.model)
