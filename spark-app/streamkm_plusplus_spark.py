from pyspark.sql import SparkSession
from pyspark.sql.functions import from_json, col
from pyspark.sql.types import ArrayType, DoubleType
from pyspark.ml.clustering import KMeans
from pyspark.ml.feature import VectorAssembler
import redis
import json

spark = (
    SparkSession.builder.appName("KafkaStreamingClustering")
    .master("spark://spark-master:7077")
    .getOrCreate()
)

kafka_df = (
    spark.readStream.format("kafka")
    .option("kafka.bootstrap.servers", "kafka:9092")
    .option("subscribe", "streaming_data")
    .load()
)

kafka_df = kafka_df.selectExpr("CAST(value AS STRING)")



schema = ArrayType(DoubleType())


parsed_df = kafka_df.select(from_json(col("value"), schema).alias("features"))

features_df = parsed_df.selectExpr(
    "features[0] as x", "features[1] as y", "features[2] as z"
)

assembler = VectorAssembler(inputCols=["x", "y", "z"], outputCol="features_vec")
assembled_df = assembler.transform(features_df).select("x", "y", "z", "features_vec")


import time

def apply_kmeans(batch_df, batch_id):
    if batch_df.count() == 0:
        return

    start_time = time.time()

    kmeans = KMeans(
        k=3, seed=42, featuresCol="features_vec", predictionCol="prediction"
    )
    model = kmeans.fit(batch_df)

    end_time = time.time()
    training_duration = end_time - start_time
    print(f"KMeans training for batch {batch_id} took {training_duration:.2f} seconds")

    clustered = model.transform(batch_df)
    centroids = model.clusterCenters()
    results = clustered.select("x", "y", "z", "prediction").collect()

    redis_client = redis.Redis(host="redis", port=6379, decode_responses=True)

    for i, row in enumerate(results):
        cluster_id = row["prediction"]
        centroid_x = centroids[cluster_id][0]
        point_key = f"clustered_point:{batch_id}:{i}"
        data = {
            "x": row["x"],
            "y": row["y"],
            "z": row["z"],
            "cluster": cluster_id,
            "centroid_x": centroid_x,
        }
        redis_client.set(point_key, json.dumps(data))

    print(f"Batch {batch_id} sent {len(results)} points to Redis.")


query = assembled_df.writeStream.foreachBatch(apply_kmeans).outputMode("append").start()

query.awaitTermination()
