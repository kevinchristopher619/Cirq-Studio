import requests
import cirq
import json
import time

GATEWAY_URL = "http://localhost:8080/api/jobs"

# 1. Create a real circuit with measurements
q0 = cirq.GridQubit(4, 4)
q1 = cirq.GridQubit(4, 5)
circuit = cirq.Circuit(
    cirq.H(q0),
    cirq.CNOT(q0, q1),
    cirq.measure(q0, q1, key='result')
)

def run_pipeline_test():
    print("🚀 Submitting Job to Go Gateway...")
    
    payload = {
        "circuit": cirq.to_json(circuit),
        "target": "generic",
        "simulation_type": "perfect",
        "repetitions": 1024,
        "return_state_vector": True
    }

    # Step 1: Submit the Job
    submit_res = requests.post(GATEWAY_URL, json=payload)
    submit_res.raise_for_status()
    
    job_data = submit_res.json()
    job_id = job_data['job_id']
    print(f"✅ Job Accepted! ID: {job_id}")
    print("⏳ Polling for results...")

    # Step 2: Poll the Gateway until COMPLETED or FAILED
    while True:
        poll_res = requests.get(f"{GATEWAY_URL}/{job_id}")
        poll_res.raise_for_status()
        
        status_data = poll_res.json()
        status = status_data['status']
        
        if status == "COMPLETED":
            print(f"\n🎉 JOB COMPLETED!")
            print(f"Backend Used: {status_data['result']['backend']}")
            print(f"Depth: {status_data['result']['depth']}")
            
            # Print the histogram nicely
            results = status_data['result']['results']
            sorted_res = dict(sorted(results.items(), key=lambda item: item[1], reverse=True))
            print(f"Histogram: {json.dumps(sorted_res, indent=2)}")
            break
            
        elif status == "FAILED":
            print(f"\n❌ JOB FAILED!")
            print(f"Error: {status_data.get('error')}")
            break
            
        else:
            # It is QUEUED or RUNNING
            print(f"   Status: {status}... checking again in 1s")
            time.sleep(1)

if __name__ == "__main__":
    run_pipeline_test()