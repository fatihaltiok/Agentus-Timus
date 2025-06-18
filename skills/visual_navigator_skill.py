import pyautogui
import logging
import openai
import base64


def click_element_on_screen(element_description: str):
    try:
        # Take a screenshot
        screenshot = pyautogui.screenshot()
        screenshot_path = 'screenshot.png'
        screenshot.save(screenshot_path)

        # Encode the screenshot in Base64
        with open(screenshot_path, "rb") as image_file:
            encoded_image = base64.b64encode(image_file.read()).decode('utf-8')

        # Create the messages payload
        messages = [
            {
                "role": "system",
                "content": "You are a multimodal LLM that can analyze images and text."
            },
            {
                "role": "user",
                "content": f"Find the coordinates of the element described as '{element_description}' in the image."
            },
            {
                "role": "user",
                "content": f"data:image/png;base64,{encoded_image}"
            }
        ]

        # Send the messages to the multimodal LLM
        response = openai.ChatCompletion.create(
            model='gpt-4',
            messages=messages
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
