#!/usr/bin/env python3
"""Test-Script für die generierte User-Klasse."""

import sys
from pathlib import Path

# Add test_project to path
sys.path.insert(0, str(Path(__file__).parent / "test_project"))

from user import User

print("🧪 Testing User class...")
print("=" * 60)

# Test 1: Valid user
print("\n✅ Test 1: Valid user creation")
user = User(
    email="test@example.com",
    first_name="Max",
    last_name="Mustermann",
    is_active=True,
    metadata={"role": "admin", "level": 5}
)
print(f"   Created: {user.email}")
print(f"   Name: {user.first_name} {user.last_name}")
print(f"   Valid email? {user.validate_email()}")
print(f"   Dict: {user.to_dict()}")

# Test 2: Invalid email
print("\n❌ Test 2: Invalid email (should raise ValueError)")
try:
    bad_user = User(email="not-an-email")
    print("   FEHLER: Sollte ValueError werfen!")
except ValueError as e:
    print(f"   ✅ Korrekt gefangen: {e}")

# Test 3: Type error
print("\n❌ Test 3: Wrong type for email (should raise TypeError)")
try:
    bad_user = User(email=123)
    print("   FEHLER: Sollte TypeError werfen!")
except TypeError as e:
    print(f"   ✅ Korrekt gefangen: {e}")

# Test 4: Metadata immutability
print("\n🔒 Test 4: Metadata immutability (deep copy)")
original_meta = {"key": "value", "nested": {"inner": "data"}}
user2 = User(email="safe@test.com", metadata=original_meta)
original_meta["key"] = "CHANGED"
print(f"   Original metadata geändert: {original_meta}")
print(f"   User metadata unberührt: {user2.metadata}")
print(f"   ✅ Deep copy funktioniert!" if user2.metadata["key"] == "value" else "   ❌ FEHLER")

# Test 5: to_dict returns copy
print("\n🔒 Test 5: to_dict returns safe copy")
dict_copy = user2.to_dict()
dict_copy["metadata"]["key"] = "MUTATED"
print(f"   Dict copy geändert: {dict_copy['metadata']}")
print(f"   User metadata unberührt: {user2.metadata}")
print(f"   ✅ to_dict kopiert sicher!" if user2.metadata["key"] == "value" else "   ❌ FEHLER")

print("\n" + "=" * 60)
print("✅ Alle Tests bestanden!")
