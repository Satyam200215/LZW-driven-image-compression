import os
import cv2
import numpy as np
import subprocess
from flask import Flask, render_template, request, redirect, url_for, send_file, flash

app = Flask(__name__)
app.secret_key = 'supersecretkey'

UPLOAD_FOLDER = 'uploads'
DECOMPRESSED_FOLDER = 'decompressed'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
if not os.path.exists(DECOMPRESSED_FOLDER):
    os.makedirs(DECOMPRESSED_FOLDER)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['DECOMPRESSED_FOLDER'] = DECOMPRESSED_FOLDER

def compress(image):
    flattened_image = image.flatten()
    dictionary_size = 256
    dictionary = {chr(i): i for i in range(dictionary_size)}
    code_word = ''
    compressed_data = []

    for pixel_value in flattened_image:
        new_code_word = code_word + chr(pixel_value)
        if new_code_word in dictionary:
            code_word = new_code_word
        else:
            compressed_data.append(dictionary[code_word])
            dictionary[new_code_word] = dictionary_size
            dictionary_size += 1
            code_word = chr(pixel_value)

    compressed_data.append(dictionary[code_word])
    original_size = len(flattened_image) * 32
    compressed_size = len(compressed_data) * 32  # Assuming 32-bit for each entry
    compression_ratio = original_size / compressed_size
    return compressed_data, dictionary, compression_ratio

def decompress(compressed_data):
    dictionary_size = 256
    inverse_dictionary = {i: chr(i) for i in range(dictionary_size)}
    code_word = chr(compressed_data.pop(0))
    decompressed_data = [code_word]

    for code in compressed_data:
        if code in inverse_dictionary:
            entry = inverse_dictionary[code]
        elif code == dictionary_size:
            entry = code_word + code_word[0]
        else:
            raise ValueError('Bad compression')
        decompressed_data.append(entry)
        inverse_dictionary[dictionary_size] = code_word + entry[0]
        dictionary_size += 1
        code_word = entry

    return ''.join(decompressed_data)

def encrypt_file(input_filepath, output_filepath, password):
    command = f"openssl enc -aes-256-cbc -salt -pbkdf2 -base64 -in \"{input_filepath}\" -out \"{output_filepath}\" -k \"{password}\""
    print(f"Executing command: {command}")
    try:
        subprocess.run(command, shell=True, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error during encryption: {e}")
        raise
    except FileNotFoundError as e:
        print(f"File not found during encryption: {e}")
        raise

def is_grayscale(image_path):
    image = cv2.imread(image_path)
    if image is None:
        raise ValueError("Error loading image.")
    if len(image.shape) < 3:
        return True
    if image.shape[2] == 1:
        return True
    b, g, r = image[:,:,0], image[:,:,1], image[:,:,2]
    if (b == g).all() and (b == r).all():
        return True
    return False

@app.route('/', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file part')
            return redirect(request.url)
        file = request.files['file']
        if file.filename == '':
            flash('No selected file')
            return redirect(request.url)
        if file:
            password = request.form['password']
            if not password:
                flash('Password is required.')
                return redirect(request.url)
            
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
            file.save(filepath)

            try:
                if not is_grayscale(filepath):
                    flash('The uploaded image is not grayscale. Please upload a valid grayscale image.')
                    return redirect(request.url)
            except ValueError as e:
                flash(str(e))
                return redirect(request.url)

            image = cv2.imread(filepath, cv2.IMREAD_GRAYSCALE)

            compressed_data, dictionary, compression_ratio = compress(image)
            decompressed_data = decompress(compressed_data)
            decompressed_int_values = [ord(char) for char in decompressed_data]

            if len(decompressed_int_values) != np.prod(image.shape):
                raise ValueError("Decompressed data length does not match the original image.")

            decompressed_image = np.array(decompressed_int_values, dtype=np.uint8).reshape(image.shape)
            decompressed_filepath = os.path.join(app.config['DECOMPRESSED_FOLDER'], 'decompressed_' + file.filename)
            cv2.imwrite(decompressed_filepath, decompressed_image)

            encrypted_filepath = filepath + '.enc'
            print(f"Encrypting file with password: {password}")
            try:
                encrypt_file(filepath, encrypted_filepath, password)
            except subprocess.CalledProcessError as e:
                return f"Encryption failed: {e}", 500
            except FileNotFoundError as e:
                return f"Encryption failed: {e}", 500

            return render_template('result.html', 
                                   original=file.filename, 
                                   decompressed='decompressed_' + file.filename,
                                   encrypted=file.filename + '.enc',
                                   original_size=image.size * image.itemsize,
                                   compressed_size=len(compressed_data),
                                   compression_ratio=compression_ratio)

    return render_template('upload.html')

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if not os.path.exists(file_path):
        flash("File not found.")
        return redirect(url_for('upload_file'))
    return send_file(file_path)

@app.route('/decompressed/<filename>')
def decompressed_file(filename):
    file_path = os.path.join(app.config['DECOMPRESSED_FOLDER'], filename)
    if not os.path.exists(file_path):
        flash("File not found.")
        return redirect(url_for('upload_file'))
    return send_file(file_path)

@app.route('/encrypted/<filename>')
def encrypted_file(filename):
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if not os.path.exists(file_path):
        flash("File not found.")
        return redirect(url_for('upload_file'))
    return send_file(file_path)

if __name__ == '__main__':
    app.run(debug=True)
