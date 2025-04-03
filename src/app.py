from flask import Flask, render_template, request
import os

app = Flask(__name__)

@app.route('/')
def index():
    # Read the contents of the files with utf-8 encoding
    config_content = read_file('/app/data/config.cfg')
    feeds_content = read_file('/app/data/feeds.cfg')
    filter_content = read_file('/app/data/filter.txt')

    return render_template('index.html', config=config_content, feeds=feeds_content, filter=filter_content)

@app.route('/', methods=['POST'])
def save():
    # Get the new content from the forms and save them
    config_content = request.form['config']
    feeds_content = request.form['feeds']
    filter_content = request.form['filter']

    write_file('/app/data/config.cfg', config_content)
    write_file('/app/data/feeds.cfg', feeds_content)
    write_file('/app/data/filter.txt', filter_content)

    return "Changes saved!"

def read_file(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        return file.read()

def write_file(file_path, content):
    with open(file_path, 'w', encoding='utf-8') as file:
        file.write(content)

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
