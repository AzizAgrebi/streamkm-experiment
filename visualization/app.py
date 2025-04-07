import redis
from flask import Flask, render_template
from flask_socketio import SocketIO
import json
import time
from threading import Thread

app = Flask(__name__)
socketio = SocketIO(app) 

r = redis.Redis(host='redis', port=6379, db=0)

def point_stream():
    """Background thread that checks Redis for new points every second"""
    while True:
        try:
            keys = r.keys('clustered_point:*')
            
            if keys:
                points = []
                for key in keys:
                    point_data = r.get(key)
                    if point_data:
                        try:
                            point = json.loads(point_data)
                            points.append(point)
                        except json.JSONDecodeError:
                            continue
                    r.delete(key) 
                
                if points:
                    centroid_x_values = [p.get('centroid_x', 0) for p in points]
                    min_x = min(centroid_x_values) if centroid_x_values else 0
                    max_x = max(centroid_x_values) if centroid_x_values else 1
                    
                    processed_points = {
                        'x': [p.get('x', 0) for p in points],
                        'y': [p.get('y', 0) for p in points],
                        'z': [p.get('z', 0) for p in points],
                        'centroid_x': centroid_x_values,
                        'min_x': min_x,
                        'max_x': max_x,
                        'count': len(points)
                    }
                    
                    socketio.emit('new_points', processed_points)
            
            time.sleep(3) 
        except Exception as e:
            print(f"Error in point_stream: {e}")
            time.sleep(3)

@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    Thread(target=point_stream, daemon=True).start()
    socketio.run(app, host='0.0.0.0', port=5000, debug=True, allow_unsafe_werkzeug=True)