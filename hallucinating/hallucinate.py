from flask import Flask, request, jsonify, render_template, redirect, url_for
import serial
import time
from collections import deque
import threading
import logging
from logging.handlers import RotatingFileHandler

app = Flask(__name__)


if not app.debug:
    # Create a file handler for the logs
    handler = RotatingFileHandler('hallucinate.log', maxBytes=10000, backupCount=3)
    handler.setLevel(logging.INFO)
    app.logger.addHandler(handler)

# Replace 'COM4' with the correct port for your Arduino
ser = serial.Serial('/dev/ttyUSB0', 9600, timeout=1)
time.sleep(2)  # Wait for the connection to initialize

# Queue and display management
text_queue = deque()
displayed_texts = deque()  # Each entry will be a tuple (text, start_time, is_scrolling_in, scroll_in_time)
panel_length = 100         # Number of characters that fit on the panel
char_scroll_time = 0.2     # Time to scroll one character across the panel in seconds
pause_time = 2             # Pause time after a text is fully displayed

# Flags to control display logic
is_scrolling_in = False  # True if a text is currently scrolling in
current_text_start_time = 0  # Time when the current text started scrolling

def send_text_to_arduino(text):
    try:
        ser.write((text + '\n').encode('latin-1'))  # Send the text to the Arduino using Latin-1 encoding
        print(f"Sent to Arduino: {text}")  # Log the text sent for debugging
        time.sleep(0.1)  # Slight delay for Arduino to process
        # Optionally, read response from Arduino if expected
        response = ser.readline().decode('latin-1').strip()
        print(f"Arduino response: {response}")
        return response
    except Exception as e:
        print(f"Error sending to Arduino: {e}")
        return None

def manage_display():
    global is_scrolling_in, current_text_start_time, displayed_texts
    
    while True:
        current_time = time.time()

        # Check if the current text is done scrolling in
        if is_scrolling_in and displayed_texts:
            scroll_in_time = displayed_texts[-1][3]  # Get the scroll-in time of the last text
            if current_time - current_text_start_time >= scroll_in_time:
                is_scrolling_in = False  # Scroll-in is complete
                displayed_texts[-1] = (displayed_texts[-1][0], current_text_start_time, False, scroll_in_time)  # Update scrolling status

        # Remove text after it has fully passed the panel
        if displayed_texts:
            remove_time = displayed_texts[0][1] + panel_length * char_scroll_time  # Calculate the time when the text should be removed
            if current_time >= remove_time:
                displayed_texts.popleft()  # Remove the text from the display

        # If no text is currently scrolling in and there's something in the queue
        if not is_scrolling_in and text_queue:
            # Move the next text from the queue to the display
            next_text = text_queue.popleft()
            current_text_start_time = time.time()  # Record the start time of this text
            scroll_in_time = len(next_text) * char_scroll_time  # Calculate scroll-in time

            displayed_texts.append((next_text, current_text_start_time, True, scroll_in_time))  # Add with scroll-in flag
            
            # Send the text to the Arduino
            send_text_to_arduino(next_text)
            is_scrolling_in = True
        
        time.sleep(0.1)  # Adjust as needed

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/status', methods=['GET'])
def status():
    # Prepare the status information
    current_texts_with_status = [
        {
            "text": text,
            "time_shown": round(time.time() - start_time, 2),
            "scrolling_in": scrolling_in,
            "scroll_in_time": scroll_in_time
        }
        for text, start_time, scrolling_in, scroll_in_time in displayed_texts
    ]
    return jsonify(current_texts=current_texts_with_status, queue=list(text_queue))

@app.route('/submit', methods=['POST'])
def submit_text():
    global is_scrolling_in, current_text_start_time
    
    # Check if the request content type is JSON
    if request.is_json:
        data = request.get_json()
        text = data.get('text')
    else:
        text = request.form['text']
    
    if not is_scrolling_in:
        # Start displaying the text immediately
        current_text_start_time = time.time()  # Record the start time
        scroll_in_time = len(text) * char_scroll_time  # Calculate scroll-in time
        
        displayed_texts.append((text, current_text_start_time, True, scroll_in_time))  # Track text with scroll-in status
        send_text_to_arduino(text)
        is_scrolling_in = True
    else:
        # Add the text to the queue
        text_queue.append(text)
    
    return redirect(url_for('index'))

if __name__ == '__main__':
    # Start the background thread to manage text display
    thread = threading.Thread(target=manage_display)
    thread.daemon = True
    thread.start()

    app.run(host='0.0.0.0', port=5000)
