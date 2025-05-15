from flask import Flask, flash, make_response, session, redirect, url_for, render_template, request, jsonify, Response
from flask_cors import CORS
from dotenv import load_dotenv
import os, json

from JiraClient import JiraClient

app = Flask(__name__)
CORS(app)

load_dotenv()
PORT = os.getenv('PORT')
DEBUG = os.getenv('DEBUG', False)

client = JiraClient()


#--------------------------------------------------------------------------------------
# Routes
#--------------------------------------------------------------------------------------

@app.route('/', methods=['GET'])
def render_menu():
    return render_template('menu.html')


@app.route('/repair', methods=['GET'])
def repair_time_page():
    return render_template('RepairTime.html') 



#--------------------------------------------------------------------------------------
# API Routes
#--------------------------------------------------------------------------------------

@app.route('/chip_count', methods=['POST'])
def chip_count():
    data = request.json()
    board_chip_count = data['chip_count']
    board_serial = data['serial']
    print(f"CHIP COUNT RECIEVED: {board_chip_count} FOR SERIAL: {board_serial}")
    
    #dummy api route for now. print to console for testing.
    return "OKAY!"

@app.route('/dump_rt_data')
def dump_rt_data():
    return client.dump_all_rt_epics_metadata()

@app.route('/get_orders')
def get_orders():
    try:
        epic_list = client.get_all_rt_epics()
        return jsonify(epic_list)
    except Exception as e:
        print(f"Error in /orders: {e}")
        return jsonify({"error": "Internal server error"}), 500
    

@app.route('/get_repair_times', methods=['POST'])
def api():
    try:
        rt_number = request.json['rt_number']

        def generate_data():
            for filtered_hb in client.get_repair_data_from_epic(rt_number):
                yield json.dumps(filtered_hb, default=str) + '\n'

        return Response(generate_data(), mimetype='application/x-ndjson')

    except Exception as e:
        print(f"Error in /api: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route('/update_board', methods=['POST'])
def update_board():
    try:
        board_data = request.json
        if not board_data:
            return jsonify({"error": "Missing board data"}), 400

        client.update_jira_with_board_data(board_data)

        return "OKAY", 200

    except Exception as e:
        print(f"Error in /update_board: {e}")
        return jsonify({"error": "Internal server error"}), 500


#--------------------------------------------------------------------------------------

@app.route('/favicon.ico')
def favicon():
    return app.send_static_file('favicon.ico')


@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404


#--------------------------------------------------------------------------------------

if __name__ == '__main__':
    app.run(host ='0.0.0.0', port=PORT, debug=DEBUG)