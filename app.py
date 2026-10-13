import os
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
import json 

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# Enable CORS for all incoming frontend origins
CORS(app)

# Configuration from environment variables
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")
SARVAM_ORG_ID = os.getenv("SARVAM_ORG_ID")
SARVAM_WORKSPACE_ID = os.getenv("SARVAM_WORKSPACE_ID")
SARVAM_APP_ID = os.getenv("SARVAM_APP_ID")
CONNECTION_ID = os.getenv("CONNECTION_ID")
AGENT_PHONE_NUMBER = os.getenv("AGENT_PHONE_NUMBER")
ACPL_AGENT_STAFF_CHECKING_APP_ID = os.getenv("ACPL_AGENT_STAFF_CHECKING_APP_ID")

# Default fallback mobile number for triggering automatic outbound calls
DEFAULT_OUTBOUND_PHONE_NUMBER = os.getenv("DEFAULT_OUTBOUND_PHONE_NUMBER", "+919841761512")

BASE_OUTBOUND_URL = f"https://apps.sarvam.ai/api/outbounds/v1/orgs/{SARVAM_ORG_ID}/workspaces/{SARVAM_WORKSPACE_ID}"
BASE_ANALYTICS_URL = f"https://apps.sarvam.ai/api/analytics/v1/{SARVAM_ORG_ID}/{SARVAM_WORKSPACE_ID}/{SARVAM_APP_ID}"


def get_headers():
    """Helper function to build Sarvam API request headers."""
    if not SARVAM_API_KEY:
        raise ValueError("SARVAM_API_KEY environment variable is missing.")
    return {
        "Content-Type": "application/json",
        "X-API-Key": SARVAM_API_KEY
    }


# Helper function to trigger Outbound Calls programmatically
def trigger_outbound_call_internal(target_phone_number, initial_variables=None, app_id=SARVAM_APP_ID):
    """Internal helper to initiate an outbound call via Sarvam API."""
    try:
        payload = {
            "app_config": {
                "app_id": app_id,
                "app_version": 1,
                "connection_config": {
                    "connection_id": CONNECTION_ID,
                    "agent_phone_number": AGENT_PHONE_NUMBER
                },
                "agent_variables": initial_variables or {}
            },
            "user_config": {
                "user_phone_number": target_phone_number
            }
        }

        print(f"[OUTBOUND] Triggering call to {target_phone_number} with variables:", json.dumps(payload, indent=2))

        response = requests.post(
            f"{BASE_OUTBOUND_URL}/outbounds",
            json=payload,
            headers=get_headers(),
            timeout=15
        )
        return response.json(), response.status_code
    except Exception as e:
        print(f"[ERROR] Failed to trigger internal outbound call: {str(e)}")
        return {"error": str(e)}, 500


# -------------------------------------------------------------------
# API Endpoint 1: Create Outbound Call (Manual API Route)
# -------------------------------------------------------------------
@app.route("/api/sarvam/outbound", methods=["POST"])
def create_outbound_call():
    """Triggers an instant outbound AI call with initial variables."""
    try:
        body = request.get_json() or {}
        variables = (
            body.get("initial_agent_variables") or 
            body.get("agent_variables") or 
            body.get("initialAgentVariables")
        )
        target_number = body.get("user_phone_number") or DEFAULT_OUTBOUND_PHONE_NUMBER

        if body.get("app_id"):
            app_id = body.get("app_id")
        else:
            app_id = SARVAM_APP_ID

        res_data, status_code = trigger_outbound_call_internal(target_number, variables, app_id)
        return jsonify(res_data), status_code

    except requests.exceptions.RequestException as e:
        error_msg = e.response.json() if e.response is not None else str(e)
        status_code = e.response.status_code if e.response is not None else 500
        return jsonify({"error": "Sarvam API request failed", "details": error_msg}), status_code


# -------------------------------------------------------------------
# Helper: Find Attempt and Interaction ID from Analytics List
# -------------------------------------------------------------------
def find_attempt_in_analytics(target_attempt_id):
    """Queries Sarvam analytics for attempt details."""
    now = datetime.now(timezone.utc)
    start_time = (now - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    end_time = (now + timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    params = {
        "start_datetime": start_time,
        "end_datetime": end_time
    }

    url = f"{BASE_ANALYTICS_URL}/attempts"
    res = requests.get(url, params=params, headers=get_headers(), timeout=15)
    
    if res.status_code != 200:
        return None, res.status_code

    attempts_data = res.json()
    print("Received Analytics Response:", attempts_data)
    attempts_list = (
        attempts_data.get("items")
        or attempts_data.get("attempts")
        or (attempts_data if isinstance(attempts_data, list) else [])
    )

    print("Found {} attempts in analytics".format(len(attempts_list)))

    for item in attempts_list:
        if item.get("attempt_id") == target_attempt_id:
            return item, 200

    return None, 404


# -------------------------------------------------------------------
# API Endpoint 2: Get Attempt Data + Transcript + Audio URL
# -------------------------------------------------------------------
@app.route("/api/sarvam/attempts/<attempt_id>", methods=["GET"])
def get_attempt_by_id(attempt_id):
    """Retrieves normalized call data, agent variables, recording, and transcript."""
    try:
        attempt_item, status_code = find_attempt_in_analytics(attempt_id)

        if not attempt_item:
            return jsonify({
                "error": "Call attempt not found",
                "attempt_id": attempt_id,
                "hint": "The call may still be processing. Please retry in a few seconds."
            }), 404

        interaction_id = attempt_item.get("interaction_id")
        transcript_data = None

        if interaction_id and interaction_id != "NO_INTERACTION_ID":
            try:
                transcript_url = f"{BASE_ANALYTICS_URL}/transcripts/{interaction_id}"
                t_res = requests.get(transcript_url, headers=get_headers(), timeout=10)
                if t_res.status_code == 200:
                    transcript_data = t_res.json()
            except Exception as t_err:
                print(f"[WARN] Transcript exception: {t_err}")

        normalized_response = {
            "attempt_id": attempt_item.get("attempt_id"),
            "interaction_id": interaction_id if interaction_id != "NO_INTERACTION_ID" else None,
            "status": attempt_item.get("connectivity_status"),
            "failure_reason": attempt_item.get("failure_reason"),
            "ended_by": attempt_item.get("ended_by"),
            "duration": attempt_item.get("duration_in_seconds"),
            "language": attempt_item.get("language_name"),
            "user_phone": attempt_item.get("user_contact"),
            "audio_url": attempt_item.get("audio_url"),
            "agent_variables": attempt_item.get("agent_variables"),
            "transcript": transcript_data,
            "raw": attempt_item
        }

        return jsonify(normalized_response), 200

    except requests.exceptions.RequestException as e:
        error_msg = e.response.json() if e.response is not None else str(e)
        status_code = e.response.status_code if e.response is not None else 500
        return jsonify({"error": "Failed to fetch attempt data", "details": error_msg}), status_code


# -------------------------------------------------------------------
# API Endpoint 3: Query Attempts by Date Range
# -------------------------------------------------------------------
@app.route("/api/sarvam/attempts", methods=["GET"])
def get_attempts_list():
    """Queries attempts across a start and end datetime range."""
    try:
        start_datetime = request.args.get("start_datetime", "2026-09-28T00:00:00.000Z")
        end_datetime = request.args.get("end_datetime", "2026-10-02T23:59:59.000Z")

        params = {
            "start_datetime": start_datetime,
            "end_datetime": end_datetime
        }

        response = requests.get(
            f"{BASE_ANALYTICS_URL}/attempts",
            params=params,
            headers=get_headers(),
            timeout=15
        )
        return (jsonify(response.json()), response.status_code)

    except requests.exceptions.RequestException as e:
        error_msg = e.response.json() if e.response is not None else str(e)
        status_code = e.response.status_code if e.response is not None else 500
        return jsonify({"error": "Failed to query attempts list", "details": error_msg}), status_code


# -------------------------------------------------------------------
# API Endpoint 4: Get Transcript by interaction_id
# -------------------------------------------------------------------
@app.route("/api/sarvam/transcripts/<interaction_id>", methods=["GET"])
def get_transcript(interaction_id):
    """Fetches the conversation transcript for a finished call interaction."""
    try:
        response = requests.get(
            f"{BASE_ANALYTICS_URL}/transcripts/{interaction_id}",
            headers=get_headers(),
            timeout=15
        )
        return (jsonify(response.json()), response.status_code)

    except requests.exceptions.RequestException as e:
        error_msg = e.response.json() if e.response is not None else str(e)
        status_code = e.response.status_code if e.response is not None else 500
        return jsonify({"error": "Failed to fetch transcript", "details": error_msg}), status_code


# -------------------------------------------------------------------
# API Endpoint 5: Get Output Variables by interaction_id
# -------------------------------------------------------------------
@app.route("/api/sarvam/interactions/<path:interaction_id>/variables", methods=["GET"])
def get_variables_by_interaction_id(interaction_id):
    """Fetches the final extracted variables and distinguishes input vs output."""
    try:
        now = datetime.now(timezone.utc)
        start_time = (now - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        end_time = (now + timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%S.000Z")

        params = {
            "start_datetime": start_time,
            "end_datetime": end_time
        }

        url = f"{BASE_ANALYTICS_URL}/attempts"
        res = requests.get(url, params=params, headers=get_headers(), timeout=15)
        
        if res.status_code != 200:
            return jsonify({"error": "Failed to query analytics", "details": res.text}), res.status_code

        attempts_data = res.json()
        attempts_list = attempts_data.get("items") or attempts_data.get("attempts") or []

        matching_attempt = None
        for item in attempts_list:
            if item.get("interaction_id") == interaction_id:
                matching_attempt = item
                break

        if not matching_attempt:
            return jsonify({
                "error": "Interaction not found",
                "interaction_id": interaction_id
            }), 404

        all_variables = matching_attempt.get("agent_variables") or {}

        input_keys = {
            "requirement_id", "vendor_name", "vendor_contact_name", "vendor_phone",
            "pickup_location", "delivery_location", "pickup_datetime",
            "vehicle_type_required", "capacity_required", "cargo_description",
            "cargo_weight", "special_requirements"
        }

        input_variables = {}
        extracted_output_variables = {}

        for key, val in all_variables.items():
            if key in input_keys:
                input_variables[key] = val
            else:
                extracted_output_variables[key] = val

        return jsonify({
            "interaction_id": interaction_id,
            "attempt_id": matching_attempt.get("attempt_id"),
            "connectivity_status": matching_attempt.get("connectivity_status"),
            "duration_in_seconds": matching_attempt.get("duration_in_seconds"),
            "ended_by": matching_attempt.get("ended_by"),
            "extracted_outputs": extracted_output_variables,
            "input_variables": input_variables,
            "all_variables": all_variables
        }), 200

    except Exception as e:
        return jsonify({"error": "Internal server error", "details": str(e)}), 500


# -------------------------------------------------------------------
# API Endpoint 6: General Webhook Receiver
# -------------------------------------------------------------------
@app.route("/api/sarvam/webhook", methods=["POST"])
def receive_call_webhook():
    """Receives automated call result webhooks sent by Sarvam."""
    webhook_data = request.get_json() or {}
    print("Received Sarvam Webhook Payload:", webhook_data)
    return jsonify({"status": "received"}), 200


# -------------------------------------------------------------------
# API Endpoint 7: Inbound Call Webhook Receiver & Automatic Outbound Trigger
# -------------------------------------------------------------------
recent_inbound_calls = []
def extract_all_variables(payload):
    """
    Extracts agent variables from all possible locations inside Sarvam/Vobiz webhooks.
    """
    # 1. Try standard variable keys in payload
    vars_dict = (
        payload.get("final_agent_variables") or 
        payload.get("agent_variables") or 
        payload.get("extracted_variables") or 
        payload.get("output_variables") or 
        {}
    )
    
    # 2. Check if variables are nested inside "data" or "result" blocks
    if not vars_dict and "data" in payload:
        data_block = payload.get("data", {})
        vars_dict = (
            data_block.get("final_agent_variables") or 
            data_block.get("agent_variables") or 
            {}
        )
        
    return vars_dict if isinstance(vars_dict, dict) else {}


@app.route("/api/sarvam/inbound-webhook", methods=["POST"])
def receive_inbound_call_webhook():
    try:
        payload = {}
        if request.is_json:
            payload = request.get_json(silent=True) or {}
        else:
            try:
                payload = json.loads(request.data.decode('utf-8'))
            except Exception:
                payload = request.form.to_dict() or {}

        print("\n================ [INBOUND CALL HANGUP WEBHOOK RECEIVED] ================")
        print(json.dumps(payload, indent=2))
        print("=======================================================================\n")

        interaction_id = payload.get("interaction_id")
        attempt_id = payload.get("attempt_id")
        caller_phone = payload.get("user_phone_number") or payload.get("user_contact")
        
        # Safely extract variables from webhook payload
        extracted_variables = extract_all_variables(payload)

        # FALLBACK: If only 'call_summary' exists or variables are missing, fetch directly from Analytics API
        if (not extracted_variables or list(extracted_variables.keys()) == ["call_summary"]) and interaction_id:
            print(f"[FETCH] Webhook payload missing deep variables. Querying Sarvam Analytics for {interaction_id}...")
            try:
                # Small wait to give Sarvam's LLM pipeline time to complete extraction
                import time
                time.sleep(1.5)
                
                analytics_url = f"{BASE_ANALYTICS_URL}/attempts"
                now = datetime.now(timezone.utc)
                params = {
                    "start_datetime": (now - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                    "end_datetime": (now + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
                }
                res = requests.get(analytics_url, params=params, headers=get_headers(), timeout=10)
                if res.status_code == 200:
                    items = res.json().get("items") or res.json().get("attempts") or []
                    for item in items:
                        if item.get("interaction_id") == interaction_id or item.get("attempt_id") == attempt_id:
                            analytics_vars = item.get("agent_variables") or {}
                            if analytics_vars:
                                extracted_variables.update(analytics_vars)
                                print("[SUCCESS] Retrieved full variables from Analytics API:", analytics_vars)
                            break
            except Exception as fetch_err:
                print(f"[WARN] Failed to fetch analytics fallback: {fetch_err}")

        processed_call_data = {
            "type": "inbound_call_completed",
            "interaction_id": interaction_id,
            "attempt_id": attempt_id,
            "user_phone": caller_phone,
            "extracted_variables": extracted_variables,
            "received_at": datetime.now(timezone.utc).isoformat()
        }

        recent_inbound_calls.insert(0, processed_call_data)
        if len(recent_inbound_calls) > 20:
            recent_inbound_calls.pop()

        # Trigger automatic outbound call on hangup with ALL extracted output variables
        outbound_target_number = caller_phone or DEFAULT_OUTBOUND_PHONE_NUMBER
        outbound_variables = {
            "inbound_caller_phone": caller_phone,
            "previous_interaction_id": interaction_id,
            **extracted_variables
        }

        print(f"[WORKFLOW] Initiating automated outbound call to {outbound_target_number} with extracted variables...")
        
        outbound_response, status_code = trigger_outbound_call_internal(
            target_phone_number=outbound_target_number,
            initial_variables=outbound_variables
        )

        return jsonify({
            "status": "success",
            "message": "Inbound hangup processed & outbound call triggered",
            "extracted_variables": extracted_variables,
            "outbound_trigger_status": status_code
        }), 200

    except Exception as e:
        print(f"[ERROR] Failed to process inbound webhook: {str(e)}")
        return jsonify({"error": "Internal server error", "details": str(e)}), 500
# -------------------------------------------------------------------
# Helper API Endpoint: Fetch Latest Inbound Calls for Frontend Polling
# -------------------------------------------------------------------
@app.route("/api/sarvam/inbound-calls/latest", methods=["GET"])
def get_latest_inbound_calls():
    """Frontend UI polls this endpoint to update UI dynamically on call completion."""
    return jsonify({
        "total": len(recent_inbound_calls),
        "latest_call": recent_inbound_calls[0] if recent_inbound_calls else None,
        "calls": recent_inbound_calls
    }), 200


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)