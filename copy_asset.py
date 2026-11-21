import os
import shutil

# Look for backup or existing local static images to verify structure
src_dir = os.path.join("static", "images")
if os.path.exists(src_dir):
    print("Static images directory already configured and available locally.")
else:
    print("Static directory not found. Please ensure files are placed in static/images/")
