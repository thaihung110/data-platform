"""
NiFi REST API client for triggering process groups.

Uses requests library directly with configuration from environment variables,
avoiding dependency on Airflow Connections and Variables.
"""

import logging
from typing import Any, Dict

import requests

from .config import config

# Configure logging
logger = logging.getLogger(__name__)


def trigger_nifi_process_group(**context) -> Dict[str, Any]:
    """
    Trigger NiFi process group to start processing.

    NiFi will handle:
    - Consuming messages from Kafka
    - Processing CSV chunks
    - Writing to destination (MinIO, etc.)

    This function:
    1. Gets the process group ID from environment variables
    2. Calls NiFi REST API to start the process group
    3. Returns the result status

    Args:
        **context: Airflow context (not used but required for PythonOperator)

    Returns:
        Dictionary with trigger result:
        {
            "status": "success",
            "nifi_pg_id": "...",
            "response_code": 200
        }

    Raises:
        Exception: If NiFi API call fails

    Note:
        NiFi REST API endpoint for starting a process group:
        PUT /nifi-api/flow/process-groups/{id}

        Body: {"id": "...", "state": "RUNNING"}
    """
    # Get NiFi configuration from environment variables
    nifi_base_url = config.NIFI_API_BASE_URL
    nifi_pg_id = config.NIFI_PROCESS_GROUP_ID
    verify_ssl = config.NIFI_VERIFY_SSL
    timeout = config.NIFI_REQUEST_TIMEOUT

    logger.info(f"Triggering NiFi process group: {nifi_pg_id}")
    logger.info(f"NiFi API URL: {nifi_base_url}")
    logger.info(
        f"NiFi will consume Kafka topic: {config.KAFKA_TOPIC_CSV_INGESTION}"
    )

    try:
        # Endpoint to start/run a process group
        # NiFi API: PUT /nifi-api/flow/process-groups/{id}
        endpoint = f"{nifi_base_url}/flow/process-groups/{nifi_pg_id}"

        # Prepare request payload (simplified - only required fields)
        # Note: state can be "RUNNING", "STOPPED", or "DISABLED"
        payload = {
            "id": nifi_pg_id,
            "state": "RUNNING",
        }

        # Make the API call
        logger.info(f"Sending PUT request to: {endpoint}")
        logger.info(f"Payload: {payload}")

        response = requests.put(
            endpoint,
            json=payload,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            verify=verify_ssl,
            timeout=timeout,
        )

        # Check response
        if response.status_code in [200, 201]:
            logger.info(
                f"✓ API call successful (status {response.status_code})"
            )

            # Verify the process group actually started
            logger.info("Verifying process group status...")

            import time

            time.sleep(2)  # Wait for state change to propagate

            # Get current flow status
            verify_endpoint = (
                f"{nifi_base_url}/flow/process-groups/{nifi_pg_id}"
            )
            verify_response = requests.get(
                verify_endpoint,
                headers={"Accept": "application/json"},
                verify=verify_ssl,
                timeout=timeout,
            )

            # Initialize running_count for return value
            running_count = None

            if verify_response.status_code == 200:
                try:
                    # Check if response has content before parsing
                    if (
                        not verify_response.text
                        or verify_response.text.strip() == ""
                    ):
                        logger.warning(
                            "Verification response is empty - cannot check processor status"
                        )
                    else:
                        flow_data = verify_response.json()

                        # Extract running count from process group flow
                        pg_flow = flow_data.get("processGroupFlow", {})
                        breadcrumb = pg_flow.get("breadcrumb", {}).get(
                            "breadcrumb", {}
                        )

                        running_count = breadcrumb.get("runningCount", 0)
                        stopped_count = breadcrumb.get("stoppedCount", 0)

                        logger.info(f"Process group status:")
                        logger.info(f"  - Running processors: {running_count}")
                        logger.info(f"  - Stopped processors: {stopped_count}")

                        if running_count > 0:
                            logger.info(
                                f"✓ Successfully triggered NiFi process group: {nifi_pg_id}"
                            )
                            logger.info(
                                f"  NiFi is now consuming from Kafka topic: {config.KAFKA_TOPIC_CSV_INGESTION}"
                            )
                        else:
                            logger.warning(
                                f"⚠ Process group triggered but no processors running"
                            )
                            logger.warning(
                                f"  This may be normal if processors are already stopped individually"
                            )

                except ValueError as json_err:
                    # JSON parsing failed - log the error and response content
                    logger.warning(
                        f"Failed to parse verification response as JSON: {json_err}"
                    )
                    logger.warning(
                        f"Response content (first 500 chars): {verify_response.text[:500]}"
                    )
                    logger.warning(
                        "Process group may still be triggered successfully. "
                        "Check NiFi UI to verify processor status."
                    )
            else:
                logger.warning(
                    f"Could not verify status (status {verify_response.status_code})"
                )

            return {
                "status": "success",
                "nifi_pg_id": nifi_pg_id,
                "response_code": response.status_code,
                "nifi_url": nifi_base_url,
                "kafka_topic": config.KAFKA_TOPIC_CSV_INGESTION,
                "running_count": (
                    running_count
                    if verify_response.status_code == 200
                    else None
                ),
            }
        else:
            error_msg = (
                f"Failed to trigger NiFi PG. "
                f"Status: {response.status_code}, "
                f"Response: {response.text}"
            )
            logger.error(f"✗ {error_msg}")
            raise Exception(error_msg)

    except requests.exceptions.RequestException as e:
        logger.error(f"✗ Network error calling NiFi API: {str(e)}")
        logger.error(f"  Process group ID: {nifi_pg_id}")
        logger.error(f"  NiFi URL: {nifi_base_url}")
        raise
    except Exception as e:
        logger.error(f"✗ Error triggering NiFi process group: {str(e)}")
        logger.error(f"  Process group ID: {nifi_pg_id}")
        raise


def get_nifi_process_group_status(
    process_group_id: str = None,
) -> Dict[str, Any]:
    """
    Get the current status of a NiFi process group.

    Args:
        process_group_id: NiFi process group ID (uses env var if not provided)

    Returns:
        Dictionary with process group status information

    Note:
        This is a utility function that can be used for monitoring.
        Not currently used in the DAG but available for future enhancements.
    """
    if process_group_id is None:
        process_group_id = config.NIFI_PROCESS_GROUP_ID

    nifi_base_url = config.NIFI_API_BASE_URL
    verify_ssl = config.NIFI_VERIFY_SSL
    timeout = config.NIFI_REQUEST_TIMEOUT

    try:
        endpoint = f"{nifi_base_url}/process-groups/{process_group_id}"

        response = requests.get(
            endpoint,
            headers={"Accept": "application/json"},
            verify=verify_ssl,
            timeout=timeout,
        )

        if response.status_code == 200:
            return response.json()
        else:
            logger.error(
                f"Failed to get PG status: {response.status_code} - {response.text}"
            )
            return {}

    except Exception as e:
        logger.error(f"Error getting NiFi PG status: {e}")
        return {}
