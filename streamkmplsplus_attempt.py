from pyspark.sql import SparkSession
from pyspark.sql.functions import from_json, col, lit
from pyspark.sql.types import ArrayType, DoubleType
from pyspark.ml.linalg import Vectors
from pyspark.ml.feature import VectorAssembler
import redis
import json
import numpy as np
from typing import List, Tuple

# Initialize Spark session
spark = SparkSession.builder \
    .appName("StreamKMPlusPlus") \
    .master("spark://spark-master:7077") \
    .getOrCreate()

# Read the streaming data from Kafka
kafka_df = spark.readStream \
    .format("kafka") \
    .option("kafka.bootstrap.servers", "kafka:9092") \
    .option("subscribe", "streaming_data") \
    .load()

# Cast the Kafka value column to string and parse JSON
schema = ArrayType(DoubleType())
parsed_df = kafka_df.select(from_json(col("value").cast("string"), schema).alias("features"))

# Split features into columns
features_df = parsed_df.selectExpr(
    "features[0] as x",
    "features[1] as y",
    "features[2] as z"
)

# Assemble features into a single vector column
assembler = VectorAssembler(inputCols=["x", "y", "z"], outputCol="features_vec")
assembled_df = assembler.transform(features_df).select("features_vec")

# StreamKM++ Implementation Parameters
M = 200  # coreset size (as suggested in the thesis)
K = 3     # number of clusters
BUCKET_SIZE = 1000  # size of buckets for merge-and-reduce

class StreamKMPlusPlus:
    def __init__(self, m: int, k: int, bucket_size: int):
        self.m = m  # coreset size
        self.k = k  # number of clusters
        self.bucket_size = bucket_size
        self.buckets = []  # List to store buckets
        self.coreset_tree = None
        self.centroids = None
    
    def process_point(self, point: np.ndarray):
        """Process a single data point using merge-and-reduce technique"""
        # Add point to B0 (first bucket)
        if not self.buckets or len(self.buckets[0]) >= self.bucket_size:
            self.buckets.insert(0, [])
        self.buckets[0].append(point)
        
        # Merge-and-reduce buckets
        i = 0
        while i < len(self.buckets) - 1 and len(self.buckets[i]) == self.bucket_size:
            # Merge two buckets
            merged = self.buckets[i] + self.buckets[i+1]
            
            # Reduce (build coreset)
            coreset = self._build_coreset(merged)
            
            # Replace with new coreset
            self.buckets[i+1] = coreset
            self.buckets[i] = []
            i += 1
    
    def _build_coreset(self, points: List[np.ndarray]) -> List[np.ndarray]:
        """Build a coreset using coreset tree structure"""
        if len(points) <= self.m:
            return points
        
        # Initialize coreset tree (simplified implementation)
        # In a real implementation, this would be a proper tree structure
        # as described in the thesis (Algorithm 2.4)
        
        # For simplicity, we'll use k-means++ seeding to select m points
        # This approximates the coreset tree behavior
        
        # Select first center uniformly at random
        centers = [points[np.random.randint(len(points))]]
        
        # Select remaining centers using k-means++ seeding
        for _ in range(1, self.m):
            distances = np.array([min(np.sum((p - c)**2) for c in centers) for p in points])
            probs = distances / np.sum(distances)
            next_center_idx = np.random.choice(len(points), p=probs)
            centers.append(points[next_center_idx])
        
        return centers
    
    def get_clusters(self) -> Tuple[List[np.ndarray], List[int]]:
        """Get current cluster centers and assignments"""
        if not self.buckets:
            return [], []
        
        # Combine all buckets to form final coreset
        final_coreset = []
        for bucket in self.buckets:
            final_coreset.extend(bucket)
        
        # If we have too many points, reduce again
        if len(final_coreset) > self.m:
            final_coreset = self._build_coreset(final_coreset)
        
        # Apply k-means++ on the final coreset (Algorithm 2.2)
        if len(final_coreset) < self.k:
            return [], []
        
        # Select first center uniformly at random
        centroids = [final_coreset[np.random.randint(len(final_coreset))]]
        
        # Select remaining centers using k-means++ seeding
        for _ in range(1, self.k):
            distances = np.array([[min(np.sum((p - c)**2) for c in centroids)] for p in final_coreset])
            probs = distances / np.sum(distances)
            next_center_idx = np.random.choice(len(final_coreset), p=probs)
            centroids.append(final_coreset[next_center_idx])
        
        # Assign all points in final coreset to nearest centroid
        assignments = []
        for point in final_coreset:
            distances = [np.sum((point - c)**2) for c in centroids]
            assignments.append(np.argmin(distances))
        
        return centroids, assignments

# Initialize StreamKM++ instance
stream_kmeans = StreamKMPlusPlus(m=M, k=K, bucket_size=BUCKET_SIZE)

# Redis client setup
redis_client = redis.Redis(host="redis", port=6379, decode_responses=True)

def process_batch(batch_df, batch_id):
    """Process each micro-batch using StreamKM++"""
    if batch_df.count() == 0:
        return
    
    # Collect points from this batch
    points = [row["features_vec"].toArray() for row in batch_df.collect()]
    
    # Process each point with StreamKM++
    for point in points:
        stream_kmeans.process_point(point)
    
    # Get current clusters
    centroids, _ = stream_kmeans.get_clusters()
    
    # Store centroids in Redis
    for i, centroid in enumerate(centroids):
        centroid_key = f"streamkm_centroid:{i}"
        data = {
            "x": float(centroid[0]),
            "y": float(centroid[1]),
            "z": float(centroid[2]),
            "cluster": i
        }
        redis_client.set(centroid_key, json.dumps(data))
    
    print(f"Processed batch {batch_id}. Current centroids stored in Redis.")

# Start streaming query
query = assembled_df.writeStream \
    .foreachBatch(process_batch) \
    .outputMode("append") \
    .start()

query.awaitTermination()