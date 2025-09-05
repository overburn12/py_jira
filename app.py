from flask import Flask, flash, make_response, session, redirect, url_for, render_template, request, jsonify, Response
from flask_cors import CORS
from dotenv import load_dotenv
import os, json, time

from JiraClient import JiraClient
from helper import logger

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
def index():
    return render_template('orderSummary.html')


@app.route('/repair', methods=['GET'])
def repair_time_page():
    return render_template('RepairTime.html') 


@app.route('/timeline', methods=['GET'])
def timeline_page():
    return render_template('Timeline.html')


@app.route('/multiorder', methods=['GET'])
def test_page():
    return render_template('multiOrder.html')


@app.route('/summary', methods=['GET'])
def summary_page():
    return render_template('orderSummary.html')


#--------------------------------------------------------------------------------------
# API Routes
#--------------------------------------------------------------------------------------


@app.route('/api/update_issues', methods=['POST'])
def api_update_issues():
    rt_key = request.json['rt_number']
    def generate_data():
        for issue in client.dump_issues_to_files(rt_key):
            yield json.dumps(issue, default=str) + '\n'
        yield json.dumps({"message": "DONE!"}, default=str) + '\n'

    return Response(generate_data(), mimetype='application/x-ndjson')


@app.route('/api/get_orders')
def api_get_orders():
    try:
        epic_list = client.get_all_rt_epics()
        return jsonify(epic_list)
    except Exception as e:
        print(f"Error in /orders: {e}")
        return jsonify({"error": "Internal server error"}), 500
    

@app.route('/api/get_repair_times', methods=['POST'])
def api_get_repair_times():
    try:
        rt_number = request.json['rt_number']

        def generate_data():
            for filtered_hb in client.get_repair_data_from_epic(rt_number):
                yield json.dumps(filtered_hb, default=str) + '\n'

        return Response(generate_data(), mimetype='application/x-ndjson')

    except Exception as e:
        print(f"Error in /get_repair_times: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route('/api/get_all_issue_summaries', methods=['POST'])
def api_get_all_issue_summaries():
    try:
        rt_number = request.json['rt_number']

        def generate_data():
            for filtered_hb in client.get_issue_summary_from_epic(rt_number):
                yield json.dumps(filtered_hb, default=str) + '\n'

        return Response(generate_data(), mimetype='application/x-ndjson')

    except Exception as e:
        print(f"Error in /get_repair_times: {e}")
        return jsonify({"error": "Internal server error"}), 500
    

@app.route('/api/get_issue_summary', methods=['POST'])
def api_get_issue_summary():
    try:
        data = request.get_json()
        epic_key = data['epic-key']
        serial = data['serial']
        return client.create_issue_summary_by_serial_from_epic(serial, epic_key)
    except Exception as e:
        logger.error(f"Error in /api/get_issue_summary: {e}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500


@app.route('/api/update_board', methods=['POST'])
def api_update_board():
    try:
        board_data = request.json
        if not board_data:
            return jsonify({"error": "Missing board data"}), 400

        client.update_jira_with_board_data(board_data)

        return "OKAY", 200

    except Exception as e:
        print(f"Error in /update_board: {e}")
        return jsonify({"error": "Internal server error"}), 500
    


@app.route('/api/create_board', methods=['POST'])
def update_board():
    try:
        board_data = request.json
        if not board_data:
            return jsonify({"error": "Missing board data"}), 400

        result = client.create_issue_if_not_exists(board_data)

        if result:
            return "OKAY", 200
        else:
            return "NOT OKAY", 200

    except Exception as e:
        print(f"Error in /update_board: {e}")
        return jsonify({"error": "Internal server error"}), 500



@app.route('/api/get_timeline', methods=['GET'])
def api_get_timeline():
    rt_key = str(request.args.get('rt'))
    if not rt_key:
        return jsonify({'error': 'RT number is required'}), 400

    try:
        data = client.create_epic_timeline_data(rt_key)
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/get_all_summaries', methods=['GET'])
def get_all_summaries():
    try:
        summary_data = client.get_all_order_summaries()
        return jsonify(summary_data)
    except Exception as e:
        return jsonify({'error': 'error in get_all_summaries'})


@app.route('/api/get_total_epic', methods=['POST'])
def api_get_total_epic():
    try:
        data = request.get_json()
        epic_key = data['epic_key']

        return jsonify(client.get_total_epic(epic_key))
    except Exception as e:
        return jsonify({'error': 'error in get_total_epic'})


@app.route('/api/get_holidays', methods=['GET'])
def api_get_holidays():
    try:
        return jsonify({'holidays': client.holidays})
    except Exception as e:
        return jsonify({'error': 'error in get_holidays'})


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