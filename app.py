import os
import time
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

# ─────────────────────────────────────────────────────────
# Configuration from environment variables
# ─────────────────────────────────────────────────────────
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")
SARVAM_ORG_ID = os.getenv("SARVAM_ORG_ID")
SARVAM_WORKSPACE_ID = os.getenv("SARVAM_WORKSPACE_ID")
SARVAM_APP_ID = os.getenv("SARVAM_APP_ID")
CONNECTION_ID = os.getenv("CONNECTION_ID")
AGENT_PHONE_NUMBER = os.getenv("AGENT_PHONE_NUMBER")
ACPL_AGENT_STAFF_CHECKING_APP_ID = os.getenv("ACPL_AGENT_STAFF_CHECKING_APP_ID")
MINI_APP_ID = "Micro-Finan-8dafac05-20e2"

# Default fallback mobile number for triggering automatic outbound calls
DEFAULT_OUTBOUND_PHONE_NUMBER = os.getenv("DEFAULT_OUTBOUND_PHONE_NUMBER", "+919841761512")

# ─────────────────────────────────────────────────────────
# Base URLs
# ─────────────────────────────────────────────────────────
BASE_OUTBOUND_URL = f"https://apps.sarvam.ai/api/outbounds/v1/orgs/{SARVAM_ORG_ID}/workspaces/{SARVAM_WORKSPACE_ID}"

# ─────────────────────────────────────────────────────────
# In-memory map: attempt_id → app_id
# This lets us know which Sarvam App each call belongs to
# ─────────────────────────────────────────────────────────
attempt_to_app_map = {}
recent_inbound_calls = []


# ─────────────────────────────────────────────────────────
# Helper: Dynamic Analytics URL Builder
# ─────────────────────────────────────────────────────────
def get_analytics_url(app_id=None):
    """Builds the Sarvam Analytics URL for a given app_id."""
    target_app_id = app_id or SARVAM_APP_ID
    return f"https://apps.sarvam.ai/api/analytics/v1/{SARVAM_ORG_ID}/{SARVAM_WORKSPACE_ID}/{target_app_id}"


def get_headers():
    """Helper function to build Sarvam API request headers."""
    if not SARVAM_API_KEY:
        raise ValueError("SARVAM_API_KEY environment variable is missing.")
    return {
        "Content-Type": "application/json",
        "X-API-Key": SARVAM_API_KEY
    }


def get_candidate_app_ids(target_app_id=None, attempt_id=None):
    """
    Returns a prioritized list of app_ids to search through.
    1. Explicitly provided app_id
    2. app_id from the attempt map (if attempt was triggered by this server)
    3. Default fallbacks: MINI_APP_ID, SARVAM_APP_ID, ACPL_AGENT_STAFF_CHECKING_APP_ID
    """
    candidates = []
    if target_app_id:
        candidates.append(target_app_id)
    if attempt_id and attempt_id in attempt_to_app_map:
        mapped = attempt_to_app_map[attempt_id]
        if mapped not in candidates:
            candidates.append(mapped)

    for default_id in [MINI_APP_ID, SARVAM_APP_ID, ACPL_AGENT_STAFF_CHECKING_APP_ID]:
        if default_id and default_id not in candidates:
            candidates.append(default_id)
    return candidates

@app.route("/api/sarvam/outboundAcpl", methods=["POST"])
def trigger_outbound_call_Acpl():
    """Internal helper to initiate an outbound call via Sarvam API."""
    # target_app_id = app_id or SARVAM_APP_ID
    body = request.get_json() or {}
    target_app_id = body.get("app_id") 
    initial_variables = body.get("initial_agent_variables")
    target_phone_number = body.get("user_phone_number")
    initial_variables ={
    # "hub_follow_up_cases": [
    #   {
    #     "gc_number": "DM 2610098421",
    #     "query": "My shipment is delayed. What is the reason?"
    #   }
    # ],
    # "hub_follow_up_required": True,
    "GCNumber": [
      "DM 2610098421"
    ],
    "CustomerQuery": [
      "My shipment is delayed. What is the reason?"
    ],
    "FromStation": [
      "Surat Ringroad"
    ],
    "Destination": [
      "Ahmedabad Sanand"
    ],
    # "customer_phone_number": "NOT_AVAILABLE"
    }
    try:
        payload = {
            "app_config": {
                "app_id": "ACPL-Cargo--48497236-b1ed",
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

        print(f"\n[OUTBOUND] App={target_app_id} → {target_phone_number}")
        print(json.dumps(payload, indent=2))

        response = requests.post(
            f"{BASE_OUTBOUND_URL}/outbounds",
            json=payload,
            headers=get_headers(),
            timeout=15
        )
        res_json = response.json()

        # Store attempt_id → app_id mapping (critical for later analytics lookup)
        att_id = res_json.get("attempt_id") or res_json.get("id")
        if att_id:
            attempt_to_app_map[att_id] = target_app_id
            print(f"[MAP] Stored attempt_id={att_id} → app_id={target_app_id}")

        return res_json, response.status_code
    except Exception as e:
        print(f"[ERROR] Failed to trigger internal outbound call: {str(e)}")
        return {"error": str(e)}, 500




# ─────────────────────────────────────────────────────────
# Helper: Trigger Outbound Call programmatically
# ─────────────────────────────────────────────────────────
def trigger_outbound_call_internal(target_phone_number, initial_variables=None, app_id=None):
    """Internal helper to initiate an outbound call via Sarvam API."""
    target_app_id = app_id or SARVAM_APP_ID
    try:
        payload = {
            "app_config": {
                "app_id": target_app_id,
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

        print(f"\n[OUTBOUND] App={target_app_id} → {target_phone_number}")
        print(json.dumps(payload, indent=2))

        response = requests.post(
            f"{BASE_OUTBOUND_URL}/outbounds",
            json=payload,
            headers=get_headers(),
            timeout=15
        )
        res_json = response.json()

        # Store attempt_id → app_id mapping (critical for later analytics lookup)
        att_id = res_json.get("attempt_id") or res_json.get("id")
        if att_id:
            attempt_to_app_map[att_id] = target_app_id
            print(f"[MAP] Stored attempt_id={att_id} → app_id={target_app_id}")

        return res_json, response.status_code
    except Exception as e:
        print(f"[ERROR] Failed to trigger internal outbound call: {str(e)}")
        return {"error": str(e)}, 500


# ─────────────────────────────────────────────────────────
# API Endpoint 1: Create Outbound Call (Manual API Route)
# ─────────────────────────────────────────────────────────
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
        app_id = body.get("app_id") or SARVAM_APP_ID

        res_data, status_code = trigger_outbound_call_internal(target_number, variables, app_id)
        return jsonify(res_data), status_code

    except requests.exceptions.RequestException as e:
        error_msg = e.response.json() if e.response is not None else str(e)
        status_code = e.response.status_code if e.response is not None else 500
        return jsonify({"error": "Sarvam API request failed", "details": error_msg}), status_code


# ─────────────────────────────────────────────────────────
# Helper: Find Attempt in Analytics (searches multiple apps)
# ─────────────────────────────────────────────────────────
def find_attempt_in_analytics(target_attempt_id, app_id=None):
    """
    Queries Sarvam analytics for attempt details.
    Searches across multiple possible app_ids to find the attempt.
    Returns: (attempt_item, matched_app_id, status_code)
    """
    now = datetime.now(timezone.utc)
    start_time = (now - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    end_time = (now + timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    params = {
        "start_datetime": start_time,
        "end_datetime": end_time
    }

    candidate_apps = get_candidate_app_ids(app_id, target_attempt_id)
    print(f"[LOOKUP] Searching for attempt_id={target_attempt_id} across apps: {candidate_apps}")

    for current_app in candidate_apps:
        try:
            url = f"{get_analytics_url(current_app)}/attempts"
            print(f"[CHECK] Searching app={current_app}")
            res = requests.get(url, params=params, headers=get_headers(), timeout=15)

            if res.status_code != 200:
                print(f"[SKIP] App={current_app} returned {res.status_code}")
                continue

            attempts_data = res.json()
            attempts_list = (
                attempts_data.get("items")
                or attempts_data.get("attempts")
                or (attempts_data if isinstance(attempts_data, list) else [])
            )

            print(f"[CHECK] App={current_app} returned {len(attempts_list)} attempts")

            for item in attempts_list:
                if item.get("attempt_id") == target_attempt_id:
                    print(f"[FOUND] attempt_id={target_attempt_id} inside app={current_app}")
                    # Cache this mapping for faster future lookups
                    attempt_to_app_map[target_attempt_id] = current_app
                    return item, current_app, 200
        except Exception as e:
            print(f"[WARN] Error searching app={current_app}: {e}")
            continue

    return None, None, 404


# ─────────────────────────────────────────────────────────
# API Endpoint 2: Get Attempt Data + Transcript + Audio URL
# ─────────────────────────────────────────────────────────
@app.route("/api/sarvam/attempts/<attempt_id>", methods=["GET"])
def get_attempt_by_id(attempt_id):
    """Retrieves normalized call data, agent variables, recording, and transcript."""
    try:
        # Optional ?app_id= query param for direct targeting
        app_id = request.args.get("app_id")

        attempt_item, matched_app_id, status_code = find_attempt_in_analytics(attempt_id, app_id)

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
                transcript_url = f"{get_analytics_url(matched_app_id)}/transcripts/{interaction_id}"
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
            "app_id": matched_app_id,
            "raw": attempt_item
        }

        return jsonify(normalized_response), 200

    except requests.exceptions.RequestException as e:
        error_msg = e.response.json() if e.response is not None else str(e)
        status_code = e.response.status_code if e.response is not None else 500
        return jsonify({"error": "Failed to fetch attempt data", "details": error_msg}), status_code


# ─────────────────────────────────────────────────────────
# API Endpoint 3: Query Attempts by Date Range
# ─────────────────────────────────────────────────────────
@app.route("/api/sarvam/attempts", methods=["GET"])
def get_attempts_list():
    """Queries attempts across a start and end datetime range."""
    try:
        start_datetime = request.args.get("start_datetime", "2026-09-28T00:00:00.000Z")
        end_datetime = request.args.get("end_datetime", "2026-10-02T23:59:59.000Z")
        app_id = request.args.get("app_id") or SARVAM_APP_ID

        params = {
            "start_datetime": start_datetime,
            "end_datetime": end_datetime
        }

        response = requests.get(
            f"{get_analytics_url(app_id)}/attempts",
            params=params,
            headers=get_headers(),
            timeout=15
        )
        return (jsonify(response.json()), response.status_code)

    except requests.exceptions.RequestException as e:
        error_msg = e.response.json() if e.response is not None else str(e)
        status_code = e.response.status_code if e.response is not None else 500
        return jsonify({"error": "Failed to query attempts list", "details": error_msg}), status_code


# ─────────────────────────────────────────────────────────
# API Endpoint 4: Get Transcript by interaction_id
# ─────────────────────────────────────────────────────────
@app.route("/api/sarvam/transcripts/<interaction_id>", methods=["GET"])
def get_transcript(interaction_id):
    """Fetches the conversation transcript for a finished call interaction."""
    try:
        app_id = request.args.get("app_id") or SARVAM_APP_ID
        response = requests.get(
            f"{get_analytics_url(app_id)}/transcripts/{interaction_id}",
            headers=get_headers(),
            timeout=15
        )
        return (jsonify(response.json()), response.status_code)

    except requests.exceptions.RequestException as e:
        error_msg = e.response.json() if e.response is not None else str(e)
        status_code = e.response.status_code if e.response is not None else 500
        return jsonify({"error": "Failed to fetch transcript", "details": error_msg}), status_code


# ─────────────────────────────────────────────────────────
# API Endpoint 5: Get Output Variables by interaction_id
# ─────────────────────────────────────────────────────────
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

        matching_attempt = None
        matched_app_id = None

        # Search across all known apps
        for current_app in get_candidate_app_ids():
            try:
                url = f"{get_analytics_url(current_app)}/attempts"
                res = requests.get(url, params=params, headers=get_headers(), timeout=15)
                if res.status_code != 200:
                    continue

                attempts_data = res.json()
                attempts_list = attempts_data.get("items") or attempts_data.get("attempts") or []

                for item in attempts_list:
                    if item.get("interaction_id") == interaction_id:
                        matching_attempt = item
                        matched_app_id = current_app
                        break
                if matching_attempt:
                    break
            except Exception as e:
                print(f"[WARN] Error searching app {current_app}: {e}")

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
            "app_id": matched_app_id,
            "connectivity_status": matching_attempt.get("connectivity_status"),
            "duration_in_seconds": matching_attempt.get("duration_in_seconds"),
            "ended_by": matching_attempt.get("ended_by"),
            "extracted_outputs": extracted_output_variables,
            "input_variables": input_variables,
            "all_variables": all_variables
        }), 200

    except Exception as e:
        return jsonify({"error": "Internal server error", "details": str(e)}), 500


# ─────────────────────────────────────────────────────────
# API Endpoint 6: General Webhook Receiver
# ─────────────────────────────────────────────────────────
@app.route("/api/sarvam/webhook", methods=["POST"])
def receive_call_webhook():
    """Receives automated call result webhooks sent by Sarvam."""
    webhook_data = request.get_json(silent=True) or {}
    print("Received Sarvam Webhook Payload:", json.dumps(webhook_data, indent=2))
    return jsonify({"status": "received"}), 200


# ─────────────────────────────────────────────────────────
# Helper: Safely extract variables from webhook payload
# ─────────────────────────────────────────────────────────
def extract_all_variables(payload):
    """
    Extracts agent variables from all possible locations inside Sarvam/Vobiz webhooks.
    """
    vars_dict = (
        payload.get("final_agent_variables") or
        payload.get("agent_variables") or
        payload.get("extracted_variables") or
        payload.get("output_variables") or
        {}
    )

    # Check if variables are nested inside "data" or "result" blocks
    if not vars_dict and "data" in payload:
        data_block = payload.get("data", {})
        vars_dict = (
            data_block.get("final_agent_variables") or
            data_block.get("agent_variables") or
            {}
        )

    return vars_dict if isinstance(vars_dict, dict) else {}


# ─────────────────────────────────────────────────────────
# API Endpoint 7: Inbound Call Webhook Receiver
# & Automatic Outbound Trigger
# ─────────────────────────────────────────────────────────
@app.route("/api/sarvam/inbound-webhook", methods=["POST"])
def receive_inbound_call_webhook():
    """
    1. Receives inbound call hangup notification from Sarvam AI.
    2. Extracts final agent output variables & call transcript safely.
    3. Triggers an automatic outbound call using default mobile number + extracted data.
    """
    try:
        # ROBUST payload parsing
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

        if payload.get("final_agent_variables").get("hub_follow_up_required") != True:
            print("[IGNORED] No follow-up required. Ignoring webhook...")
            return jsonify({"status": "ignored"}), 200

        interaction_id = payload.get("interaction_id")
        attempt_id = payload.get("attempt_id")
        caller_phone = payload.get("user_phone_number") or payload.get("user_contact")
        inbound_app_id = payload.get("app_id") or MINI_APP_ID

        # Safely extract variables from webhook payload
        extracted_variables = extract_all_variables(payload)

        # FALLBACK: If variables are missing, fetch directly from Analytics API
        if (not extracted_variables or list(extracted_variables.keys()) == ["call_summary"]) and interaction_id:
            print(f"[FETCH] Webhook missing deep variables. Querying Analytics for {interaction_id}...")
            try:
                time.sleep(1.5)  # Allow Sarvam LLM pipeline to finish extraction

                now = datetime.now(timezone.utc)
                params = {
                    "start_datetime": (now - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                    "end_datetime": (now + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
                }

                # Search all candidate apps for this interaction
                for current_app in get_candidate_app_ids(inbound_app_id, attempt_id):
                    analytics_url = f"{get_analytics_url(current_app)}/attempts"
                    res = requests.get(analytics_url, params=params, headers=get_headers(), timeout=10)
                    if res.status_code != 200:
                        continue

                    items = res.json().get("items") or res.json().get("attempts") or []
                    found = False
                    for item in items:
                        if item.get("interaction_id") == interaction_id or item.get("attempt_id") == attempt_id:
                            analytics_vars = item.get("agent_variables") or {}
                            if analytics_vars:
                                extracted_variables.update(analytics_vars)
                                print(f"[SUCCESS] Retrieved variables from app={current_app}:", analytics_vars)
                                found = True
                            break
                    if found:
                        break
            except Exception as fetch_err:
                print(f"[WARN] Failed to fetch analytics fallback: {fetch_err}")

        processed_call_data = {
            "type": "inbound_call_completed",
            "interaction_id": interaction_id,
            "attempt_id": attempt_id,
            "user_phone": caller_phone,
            "extracted_variables": extracted_variables,
            "received_at": datetime.now(timezone.utc).isoformat(),
            "raw_payload": payload
        }

        recent_inbound_calls.insert(0, processed_call_data)
        if len(recent_inbound_calls) > 20:
            recent_inbound_calls.pop()

        # Trigger automatic outbound call on hangup
        outbound_target_number = DEFAULT_OUTBOUND_PHONE_NUMBER
        outbound_variables = {
            "GCNumber":extracted_variables.get("gc_numbers_requiring_hub_follow_up"),
            "CustomerQuery":extracted_variables.get("customer_queries_requiring_hub_follow_up"),
            "FromStation":extracted_variables.get("hub_issue_from_location"),
            "Destination":extracted_variables.get("hub_issue_to_location"),
            "customer_number":caller_phone,
            # "previous_interaction_id": interaction_id,

        }

        # Pick the outbound app_id (default: ACPL or MINI)
        outbound_app_id = ACPL_AGENT_STAFF_CHECKING_APP_ID or SARVAM_APP_ID

        print(f"[WORKFLOW] Triggering automated outbound call to {outbound_target_number} using app={outbound_app_id}")

        outbound_response, status_code = trigger_outbound_call_internal(
            target_phone_number=outbound_target_number,
            initial_variables=outbound_variables,
            app_id=outbound_app_id
        )

        return jsonify({
            "status": "success",
            "message": "Inbound hangup processed & outbound call triggered",
            "inbound_interaction_id": interaction_id,
            "extracted_variables": extracted_variables,
            "outbound_trigger_status": status_code,
            "outbound_response": outbound_response
        }), 200

    except Exception as e:
        print(f"[ERROR] Failed to process inbound webhook: {str(e)}")
        return jsonify({"error": "Internal server error", "details": str(e)}), 500

@app.route("/api/sarvam/aiOutbound-webhook", methods=["POST"])
def receive_ai_outbound_call_webhook():
    """
    1. Receives inbound call hangup notification from Sarvam AI.
    2. Extracts final agent output variables & call transcript safely.
    3. Triggers an automatic outbound call using default mobile number + extracted data.
    """
    try:
        # ROBUST payload parsing
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

        print("[CHECK] Validating webhook...")
        print("Payload received:", payload)

        # return
        # if not validate_webhook(payload):
        #     print("[IGNORED] Invalid webhook. Ignoring webhook...")
        #     return jsonify({"status": "ignored"}), 200

        # if payload.get("final_agent_variables").get("hub_follow_up_required") != True:
        #     print("[IGNORED] No follow-up required. Ignoring webhook...")
        #     return jsonify({"status": "ignored"}), 200

        interaction_id = payload.get("interaction_id")
        # attempt_id = payload.get("attempt_id")
        # caller_phone = payload.get("user_phone_number") or payload.get("user_contact")
        # inbound_app_id = payload.get("app_id") or MINI_APP_ID

        # Safely extract variables from webhook payload
        # extracted_variables = extract_all_variables(payload)
        extracted_variables = payload

        # FALLBACK: If variables are missing, fetch directly from Analytics API
        # if (not extracted_variables or list(extracted_variables.keys()) == ["call_summary"]) and interaction_id:
        #     print(f"[FETCH] Webhook missing deep variables. Querying Analytics for {interaction_id}...")
        #     try:
        #         time.sleep(1.5)  # Allow Sarvam LLM pipeline to finish extraction

        #         now = datetime.now(timezone.utc)
        #         params = {
        #             "start_datetime": (now - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        #             "end_datetime": (now + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        #         }

        #         # Search all candidate apps for this interaction
        #         for current_app in get_candidate_app_ids(inbound_app_id, attempt_id):
        #             analytics_url = f"{get_analytics_url(current_app)}/attempts"
        #             res = requests.get(analytics_url, params=params, headers=get_headers(), timeout=10)
        #             if res.status_code != 200:
        #                 continue

        #             items = res.json().get("items") or res.json().get("attempts") or []
        #             found = False
        #             for item in items:
        #                 if item.get("interaction_id") == interaction_id or item.get("attempt_id") == attempt_id:
        #                     analytics_vars = item.get("agent_variables") or {}
        #                     if analytics_vars:
        #                         extracted_variables.update(analytics_vars)
        #                         print(f"[SUCCESS] Retrieved variables from app={current_app}:", analytics_vars)
        #                         found = True
        #                     break
        #             if found:
        #                 break
        #     except Exception as fetch_err:
        #         print(f"[WARN] Failed to fetch analytics fallback: {fetch_err}")

        # processed_call_data = {
        #     "type": "inbound_call_completed",
        #     "interaction_id": interaction_id,
        #     "attempt_id": attempt_id,
        #     "user_phone": caller_phone,
        #     "extracted_variables": extracted_variables,
        #     "received_at": datetime.now(timezone.utc).isoformat(),
        #     "raw_payload": payload
        # }

        # recent_inbound_calls.insert(0, processed_call_data)
        # if len(recent_inbound_calls) > 20:
        #     recent_inbound_calls.pop()

        # Trigger automatic outbound call on hangup
        outbound_target_number = extracted_variables.get("customer_number")
        outbound_variables = {
            "gc_number":extracted_variables.get("GCNumber"),
            "CauseofDeliveryDelay":extracted_variables.get("CauseOfDeliveryDelay"),
            "customer_querry":extracted_variables.get("customer_querry"),
            "Input_to_the_customer":extracted_variables.get("Input_to_the_customer"),
            "NextTrackingUpdate":extracted_variables.get("NextTrackingUpdate"),
            # "previous_interaction_id": interaction_id,

        }

        # Pick the outbound app_id (default: ACPL or MINI)
        outbound_app_id = "ACPL-Cargo--fe38850b-6a9b" or SARVAM_APP_ID

        print(f"[WORKFLOW] Triggering automated outbound call to {outbound_target_number} using app={outbound_app_id}")

        outbound_response, status_code = trigger_outbound_call_internal(
            target_phone_number=outbound_target_number,
            initial_variables=outbound_variables,
            app_id=outbound_app_id
        )

        return jsonify({
            "status": "success",
            "message": "Inbound hangup processed & outbound call triggered",
            # "inbound_interaction_id": interaction_id,
            "extracted_variables": extracted_variables,
            "outbound_trigger_status": status_code,
            "outbound_response": outbound_response
        }), 200

    except Exception as e:
        print(f"[ERROR] Failed to process inbound webhook: {str(e)}")
        return jsonify({"error": "Internal server error", "details": str(e)}), 500


# ─────────────────────────────────────────────────────────
# API Endpoint 8: Fetch Latest Inbound Calls (frontend poll)
# ─────────────────────────────────────────────────────────
@app.route("/api/sarvam/inbound-calls/latest", methods=["GET"])
def get_latest_inbound_calls():
    """Frontend UI polls this endpoint to update UI dynamically on call completion."""
    return jsonify({
        "total": len(recent_inbound_calls),
        "latest_call": recent_inbound_calls[0] if recent_inbound_calls else None,
        "calls": recent_inbound_calls
    }), 200


# ─────────────────────────────────────────────────────────
# API Endpoint 9: Debug - View Current Attempt → App Map
# ─────────────────────────────────────────────────────────
@app.route("/api/sarvam/debug/map", methods=["GET"])
def view_attempt_map():
    """Debug endpoint to inspect in-memory attempt_id → app_id map."""
    return jsonify({
        "total_mapped": len(attempt_to_app_map),
        "map": attempt_to_app_map
    }), 200


# ─────────────────────────────────────────────────────────
# Run Flask
# ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=True, threaded=True)