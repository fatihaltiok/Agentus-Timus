import random
import sys

# Eingebaute Wortliste (deutsche Wörter)
WORD_LIST = [
    "PROGRAMMIEREN", "KI", "HALLE", "BÜCHER", "SCHLAFEN", "FAHRRAD",
    "KÜCHE", "BÜNEN", "FAHRT", "SCHULE", "KINO", "BÄR", "BÄRLICH",
    "MÜSLI", "KÄSE", "PIZZA", "SCHNITT", "KARTE", "TÜCHEN", "SPIEL"
]

# ASCII-Galgenstufen (0 falsche Versuche bis zum Ende)
GALLOWES = [
    """
     +---+
     |   |
         |
         |
         |
         |
    =========
    """,
    """
     +---+
     |   |
     O   |
         |
         |
         |
    =========
    """,
    """
     +---+
     |   |
     O   |
     |   |
         |
         |
    =========
    """,
    """
     +---+
     |   |
     O   |
    /|   |
         |
         |
    =========
    """,
    """
     +---+
     |   |
     O   |
    /|\\  |
         |
         |
    =========
    """,
    """
     +---+
     |   |
     O   |
    /|\\  |
    /    |
         |
    =========
    """,
    """
     +---+
     |   |
     O   |
    /|\\  |
    / \\  |
         |
    =========
    """
]

MAX_WRONG = len(GALLOWES) - 1

def choose_word() -> str:
    """Wählt zufällig ein Wort aus WORD_LIST."""
    return random.choice(WORD_LIST)

def display_state(gallow_stage: int, guessed_letters: set, secret_word: str):
    """Zeigt den aktuellen Zustand des Spiels an."""
    print(GALLOWES[gallow_stage])
    # Wort mit Leerstellen anzeigen
    displayed = [letter if letter in guessed_letters else "_" for letter in secret_word]
    print(" ".join(displayed))
    # bereits geratene Buchstaben
    print("Buchstaben, die Sie bereits geraten haben: " + " ".join(sorted(guessed_letters)))
    print()

def get_valid_input(guessed_letters: set) -> str:
    """Fragt den Benutzer nach einer gültigen Eingabe."""
    while True:
        guess = input("Rate einen Buchstaben: ").strip().upper()
        if len(guess) != 1:
            print("Bitte geben Sie genau einen Buchstaben ein.")
            continue
        if not guess.isalpha():
            print("Bitte geben Sie einen alphabetischen Buchstaben ein.")
            continue
        if guess in guessed_letters:
            print("Sie haben diesen Buchstaben bereits geraten. Versuchen Sie einen anderen.")
            continue
        return guess

def play_game():
    secret_word = choose_word()
    guessed_letters = set()
    wrong_guesses = 0

    while True:
        display_state(wrong_guesses, guessed_letters, secret_word)

        # Gewinnüberprüfung
        if all(letter in guessed_letters for letter in secret_word):
            print(f"Glückwunsch! Sie haben das Wort '{secret_word}' erraten.")
            break

        # Verlustüberprüfung
        if wrong_guesses >= MAX_WRONG:
            print(f"Schade! Sie haben das Wort '{secret_word}' nicht erraten.")
            print("Das richtige Wort war: " + secret_word)
            break

        guess = get_valid_input(guessed_letters)
        guessed_letters.add(guess)

        if guess not in secret_word:
            wrong_guesses += 1
            print(f"Leider nicht! Sie haben {wrong_guesses} von {MAX_WRONG} Fehlversuchen benutzt.")
        else:
            print(f"Richtig! Der Buchstabe '{guess}' ist im Wort enthalten.")

        print("\n" + "-" * 40 + "\n")

def main():
    print("Willkommen beim Hangman-Spiel!")
    while True:
        play_game()
        # Neustartoption
        while True:
            restart = input("Möchten Sie erneut spielen? (j/n): ").strip().lower()
            if restart == 'j':
                break
            elif restart == 'n':
                print("Danke fürs Spielen! Auf Wiedersehen.")
                sys.exit(0)
            else:
                print("Bitte geben Sie 'j' für Ja oder 'n' für Nein ein.")

if __name__ == "__main__":
    main()