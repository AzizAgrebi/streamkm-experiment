from the root, se the commands :

docker compose build

docker compose up -d

docker exec -it streamkm-experiment-spark-master-1 spark-submit --master spark://spark-master:7077 --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0 /spark-app/streamkm_plusplus_spark.py

You can go to the http://localhost:5000/ to see the results of the front (it's updated every 3 seconds).