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


# -------------------------------------------------------------------
# API Endpoint 1: Create Outbound Call
# -------------------------------------------------------------------
@app.route("/api/sarvam/outbound", methods=["POST"])
def create_outbound_call():
    """Triggers an instant outbound AI call with initial variables."""
    try:
        body = request.get_json() or {}

        # --------------------------------------------------------------
        # CRITICAL FIX: Sarvam requires "initial_agent_variables"
        # --------------------------------------------------------------
        variables = (
            body.get("initial_agent_variables") or 
            body.get("agent_variables") or 
            body.get("initialAgentVariables")
        )

        # if variables and isinstance(variables, dict):
        #     payload["initial_agent_variables"] = variables


        payload = {
            "app_config": {
                "app_id": body.get("app_id", SARVAM_APP_ID),
                "app_version": body.get("app_version", 1),
                "connection_config": {
                    "connection_id": body.get("connection_id", "Vobiz-Secur-32799d0c-2d55"),
                    "agent_phone_number": body.get("agent_phone_number", "+918071581516")
                },
                "agent_variables": variables

            },
            "user_config": {
                "user_phone_number": body.get("user_phone_number")
            }
        }


        if "webhook_config" in body:
            payload["webhook_config"] = body["webhook_config"]

        print("Sending Payload to Sarvam:", json.dumps(payload, indent=2))

        response = requests.post(
            f"{BASE_OUTBOUND_URL}/outbounds",
            json=payload,
            headers=get_headers(),
            timeout=15
        )

        return (jsonify(response.json()), response.status_code)

    except requests.exceptions.RequestException as e:
        error_msg = e.response.json() if e.response is not None else str(e)
        status_code = e.response.status_code if e.response is not None else 500
        return jsonify({"error": "Sarvam API request failed", "details": error_msg}), status_code

# -------------------------------------------------------------------
# Helper: Find Attempt and Interaction ID from Analytics List
# -------------------------------------------------------------------
def find_attempt_in_analytics(target_attempt_id):
    """
    Queries Sarvam analytics and searches the 'items' array
    for the specific attempt_id.
    """
    now = datetime.now(timezone.utc)
    start_time = (now - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    end_time = (now + timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    params = {
        "start_datetime": start_time,
        "end_datetime": end_time
    }

    url = f"{BASE_ANALYTICS_URL}/attempts"
    print(f"[DEBUG] Fetching attempts from {url}")

    res = requests.get(url, params=params, headers=get_headers(), timeout=15)
    
    if res.status_code != 200:
        print(f"[ERROR] Sarvam returned {res.status_code}: {res.text}")
        return None, res.status_code

    attempts_data = res.json()
    print(attempts_data)

    # FIX: Sarvam uses "items" as the key!
    attempts_list = (
        attempts_data.get("items")
        or attempts_data.get("attempts")
        or (attempts_data if isinstance(attempts_data, list) else [])
    )

    print(f"[DEBUG] Found {len(attempts_list)} attempts in range.")

    # Search for the target attempt_id
    for item in attempts_list:
        if item.get("attempt_id") == target_attempt_id:
            return item, 200

    return None, 404


# -------------------------------------------------------------------
# API Endpoint 2: Get Attempt Data by attempt_id
# -------------------------------------------------------------------
# @app.route("/api/sarvam/attempts/<attempt_id>", methods=["GET"])
# def get_attempt_by_id(attempt_id):
#     """Retrieves call attempt metadata for a specific attempt_id."""
#     try:
#         response = requests.get(
#             f"{BASE_ANALYTICS_URL}/attempts/{attempt_id}",
#             headers=get_headers(),
#             timeout=15
#         )
#         return (jsonify(response.json()), response.status_code)

#     except requests.exceptions.RequestException as e:
#         error_msg = e.response.json() if e.response is not None else str(e)
#         status_code = e.response.status_code if e.response is not None else 500
#         return jsonify({"error": "Failed to fetch attempt data", "details": error_msg}), status_code

# -------------------------------------------------------------------
# API Endpoint 2: Get Attempt Data by attempt_id (FIXED)
# -------------------------------------------------------------------
# @app.route("/api/sarvam/attempts/<attempt_id>", methods=["GET"])
# def get_attempt_by_id(attempt_id):
#     """Retrieves call attempt metadata for a specific attempt_id."""
#     try:
#         # 1. Primary check: Query the Outbound API (where the call was created)
#         outbound_url = f"{BASE_OUTBOUND_URL}/outbounds/{attempt_id}"
#         print(f"[DEBUG] Fetching call status from: {outbound_url}")

#         response = requests.get(
#             outbound_url,
#             headers=get_headers(),
#             timeout=15
#         )

#         # 2. If Outbound API returns 200, return data immediately
#         if response.status_code == 200:
#             return jsonify(response.json()), 200

#         # 3. Fallback: If 404 on outbound, attempt checking Analytics API
#         analytics_url = f"https://apps.sarvam.ai/api/analytics/v1/orgs/{SARVAM_ORG_ID}/workspaces/{SARVAM_WORKSPACE_ID}/apps/{SARVAM_APP_ID}/attempts/{attempt_id}"
#         print(f"[DEBUG] Fallback checking analytics: {analytics_url}")
        
#         fallback_res = requests.get(
#             analytics_url,
#             headers=get_headers(),
#             timeout=15
#         )

#         if fallback_res.status_code == 200:
#             return jsonify(fallback_res.json()), 200

#         # Return the original error if neither succeeded
#         return jsonify({
#             "error": "Call attempt not found (404)",
#             "attempt_id": attempt_id,
#             "sarvam_response": response.json() if response.headers.get("content-type") == "application/json" else response.text
#         }), 404

#     except requests.exceptions.RequestException as e:
#         error_msg = e.response.json() if e.response is not None else str(e)
#         status_code = e.response.status_code if e.response is not None else 500
#         return jsonify({"error": "Failed to fetch attempt data", "details": error_msg}), status_code

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

        # Fetch transcript if a valid interaction_id exists (not 'NO_INTERACTION_ID')
        if interaction_id and interaction_id != "NO_INTERACTION_ID":
            try:
                # ⚠️ URL-encode the interaction_id because it contains slashes like '20261001/f65e9a24...'
                # encoded_interaction_id = urllib.parse.quote(interaction_id, safe='')
                transcript_url = f"{BASE_ANALYTICS_URL}/transcripts/{interaction_id}"
                
                t_res = requests.get(transcript_url, headers=get_headers(), timeout=10)
                if t_res.status_code == 200:
                    transcript_data = t_res.json()
                else:
                    print(f"[WARN] Transcript fetch failed ({t_res.status_code}): {t_res.text}")
            except Exception as t_err:
                print(f"[WARN] Transcript exception: {t_err}")

        # Construct a clean, normalized response object for the frontend
        normalized_response = {
            "attempt_id": attempt_item.get("attempt_id"),
            "interaction_id": interaction_id if interaction_id != "NO_INTERACTION_ID" else None,
            "status": attempt_item.get("connectivity_status"),        # 'connected', 'failed', etc.
            "failure_reason": attempt_item.get("failure_reason"),
            "ended_by": attempt_item.get("ended_by"),                # 'USER_ENDS', 'AGENT_ENDS'
            "duration": attempt_item.get("duration_in_seconds"),     # e.g., 6.30
            "language": attempt_item.get("language_name"),           # 'Tamil'
            "user_phone": attempt_item.get("user_contact"),          # '+919841761512'
            "audio_url": attempt_item.get("audio_url"),              # Direct playable link
            "agent_variables": attempt_item.get("agent_variables"),  # Extracted variables dict
            "transcript": transcript_data,                           # Call transcript
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
# API Endpoint: Get Output Variables by interaction_id
# -------------------------------------------------------------------
@app.route("/api/sarvam/interactions/<path:interaction_id>/variables", methods=["GET"])
def get_variables_by_interaction_id(interaction_id):
    """
    Fetches the final extracted variables and distinguishes between
    Input variables and Extracted Output variables.
    """
    try:
        # 1. Query Sarvam analytics for attempts in the last 24 hours
        now = datetime.now(timezone.utc)
        start_time = (now - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        end_time = (now + timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%S.000Z")

        params = {
            "start_datetime": start_time,
            "end_datetime": end_time
        }
        print(interaction_id)

        url = f"{BASE_ANALYTICS_URL}/attempts"
        res = requests.get(url, params=params, headers=get_headers(), timeout=15)
        
        if res.status_code != 200:
            return jsonify({"error": "Failed to query analytics", "details": res.text}), res.status_code

        attempts_data = res.json()
        attempts_list = attempts_data.get("items") or attempts_data.get("attempts") or []

        # 2. Find the attempt matching the interaction_id
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

        # 3. Extract variables
        all_variables = matching_attempt.get("agent_variables") or {}

        # 4. Separate initial inputs vs AI extracted outputs
        # (Customize input keys based on what you pass initially)
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
            # Cleanly separated results:
            "extracted_outputs": extracted_output_variables,
            "input_variables": input_variables,
            "all_variables": all_variables
        }), 200

    except Exception as e:
        return jsonify({"error": "Internal server error", "details": str(e)}), 500
# -------------------------------------------------------------------
# API Endpoint 5: Webhook Endpoint (Optional / Incoming from Sarvam)
# -------------------------------------------------------------------
@app.route("/api/sarvam/webhook", methods=["POST"])
def receive_call_webhook():
    """Receives automated call result webhooks sent by Sarvam when a call completes."""
    webhook_data = request.get_json() or {}
    print("Received Sarvam Webhook Payload:", webhook_data)
    
    # Process call completion logic, save to DB, etc.
    return jsonify({"status": "received"}), 200


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)

