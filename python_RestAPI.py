from flask import Flask, render_template, request, redirect, url_for

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/open', methods=['POST'])
def open_connection():
    # tu das kod na inicializaciu: otvorenie serial portu, nacitanie senzorov atd.
    print("Systém inicializovaný.")
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

