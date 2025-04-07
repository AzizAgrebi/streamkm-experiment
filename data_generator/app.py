import numpy as np
import json
from kafka import KafkaProducer
import time
from kafka.errors import NoBrokersAvailable
from time import sleep

def generate_cluster_points(center, n_points, std=0.5):
    return [center + np.random.randn(len(center)) * std for _ in range(n_points)]

def main():
    for _ in range(12):
        try:
            producer = KafkaProducer(
                bootstrap_servers=["kafka:9092"],
                value_serializer=lambda x: json.dumps(x).encode("utf-8")
            )
            break
        except NoBrokersAvailable:
            print("Waiting for Kafka...")
            sleep(10)
    else:
        raise RuntimeError("Failed to connect to Kafka after 2 minutes")
    
    true_centers = [
        np.array([0.0, 0.0, 0.0]),
        np.array([-3.0, -3.0, -3.0]),
        np.array([3.0, 3.0, 3.0])
    ]
    
    while True:
        center = true_centers[np.random.randint(0, 3)]
        points = generate_cluster_points(center, n_points=500)
        
        for point in points:
            producer.send("streaming_data", value=point.tolist())
        
        time.sleep(1)

if __name__ == "__main__":
    main()
