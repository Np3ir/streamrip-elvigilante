import time
import sys
import os

# Add the site-packages directory to path
sys.path.append(r"c:\Users\DJELVIGILANTE\AppData\Local\Programs\Python\Python313\Lib\site-packages")

from streamrip.progress import get_progress_callback, clear_progress

def simulate_download(filename, size, speed_delay):
    print(f"Starting download: {filename}")
    handle = get_progress_callback(True, size, filename)
    
    downloaded = 0
    chunk_size = 1024 * 1024  # 1MB chunks
    
    with handle as update:
        while downloaded < size:
            time.sleep(speed_delay)
            downloaded += chunk_size
            if downloaded > size:
                downloaded = size
            update(chunk_size)
    
    # After 'with' block, _done() is called.
    # In this version, the task should REMAIN VISIBLE.
    print(f"Finished download: {filename} (Task should REMAIN VISIBLE)")
    time.sleep(0.5) 

def main():
    print("Restoring original minimalist progress bar...")
    
    files = [
        ("Long Name Song 1 - Artist Name - Album Name - Very Long Title Indeed.flac", 10 * 1024 * 1024, 0.05),
        ("Short.flac", 5 * 1024 * 1024, 0.1),
    ]
    
    for name, size, delay in files:
        simulate_download(name, size, delay)
        
    clear_progress()
    print("Test complete.")

if __name__ == "__main__":
    main()
