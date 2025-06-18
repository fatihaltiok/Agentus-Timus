import pyautogui
import logging
import openai


def click_element_on_screen(element_description: str):
    try:
        # Take a screenshot
        screenshot = pyautogui.screenshot()
        screenshot_path = 'screenshot.png'
        screenshot.save(screenshot_path)

        # Send the screenshot and description to the multimodal LLM
        response = openai.Completion.create(
            engine='text-davinci-002',
            prompt=f'Find the coordinates of the element described as "{element_description}" in the image.',
            max_tokens=50
        )

        # Extract coordinates from the response
        coordinates = response.choices[0].text.strip()
        
        try:
            x, y = map(int, coordinates.split(','))
            # Click at the coordinates
            pyautogui.click(x, y)
        except ValueError:
            logging.error("Invalid coordinates received: %s", coordinates)
            print("Error: Could not find valid coordinates for the element.")
        except pyautogui.FailSafeException:
            logging.error("FailSafeException triggered at coordinates: (%d, %d)", x, y)
            print("Error: FailSafeException triggered, mouse moved to a corner.")

    except Exception as e:
        logging.error("An error occurred: %s", e)
        print(f"An error occurred: {e}")
