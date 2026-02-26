from src.mcpguard.engine import SecurityEngine

print(f"/n Testing Path Sandboxing....")

engine = SecurityEngine()
print(f"Root directory for testing: {engine.workspace_root}\n")

safe_file = str(engine.workspace_root / "allowed_document.txt")

sneaky_file = "../src/mcpguard/engine.py"

bold_file = "/etc/passwd"

print("Testing safe file access...")
assert engine.is_path_safe(safe_file) == True, "Bug: Engine blocked a safe file!"

print("Testing sneaky hacker file(../src)...")
assert engine.is_path_safe(sneaky_file) == False, "Security Flaw: Engine allowed access to src code!"

print("Testing bold hacker file (/etc/passwd)...")
assert engine.is_path_safe(bold_file) == False, "Security Flaw: Engine allowed access to root system!"

print("\nAll sandbox tests passed!")

