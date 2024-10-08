from flask import Flask, request, jsonify
from flask_httpauth import HTTPBasicAuth
from werkzeug.security import generate_password_hash, check_password_hash
import random
import requests
import os
import base64

app = Flask(__name__)
auth = HTTPBasicAuth()

user_root_dir = os.getcwd()
current_directory = user_root_dir

users = {
    "admin": generate_password_hash("adminpass"),
    "user1": generate_password_hash("password123")
}

@auth.verify_password
def verify_password(username, password):
    if username in users and check_password_hash(users.get(username), password):
        return username
    return None

data_nodes = ['http://3.221.51.224:5001', 'http://3.233.95.99:5002', 'http://34.198.142.150:5003']

metadatos = {}

@app.route('/put', methods=['POST'])
@auth.login_required
def put():
    file = request.files['file']
    filename = file.filename
    content = file.read()

    bloques = [content[i:i + 1024] for i in range(0, len(content), 1024)]

    ubicaciones = {}
    
    for i, bloque in enumerate(bloques):
        bloque_data = base64.b64encode(bloque).decode('utf-8')
        almacenado = False

        nodos_disponibles = list(data_nodes)
        
        while nodos_disponibles and not almacenado:
            try:
                primary_datanode = random.choice(nodos_disponibles)
                nodos_disponibles.remove(primary_datanode)
                
                block_id = f'{filename}_block{i}'
                file_path = os.path.join(current_directory, block_id)

                response = requests.post(f'{primary_datanode}/store', json={'blockId': f'{filename}_block{i}', 'data': bloque_data})
                if response.status_code == 200:
                    ubicaciones[i] = {'leader': primary_datanode, 'follower': None}
                    almacenado = True
                    print(f"Bloque {i} almacenado exitosamente en el líder {primary_datanode}")

                    follower_almacenado = False
                    while nodos_disponibles and not follower_almacenado:
                        follower_datanode = random.choice(nodos_disponibles)
                        nodos_disponibles.remove(follower_datanode)

                        try:
                            follower_response = requests.post(f'{follower_datanode}/store', json={'blockId': f'{filename}_block{i}', 'data': bloque_data})
                            if follower_response.status_code == 200:
                                ubicaciones[i]['follower'] = follower_datanode
                                follower_almacenado = True
                                print(f"Bloque {i} replicado exitosamente en el follower {follower_datanode}")
                        except requests.exceptions.RequestException:
                            print(f"Error replicando bloque {i} en el follower {follower_datanode}, intentando con otro nodo...")
            except requests.exceptions.RequestException:
                print(f"Error almacenando bloque {i} en el líder {primary_datanode}, intentando con otro nodo...")

        if not almacenado:
            return jsonify({'error': f'No se pudo almacenar el bloque {i}'}), 500

    metadatos[filename] = ubicaciones
    return jsonify({'message': f'{filename} subido con éxito', 'ubicaciones': ubicaciones})


@app.route('/get/<filename>', methods=['GET'])
@auth.login_required
def get(filename):
    if filename in metadatos:
        file_data = b''
        for i, datanode_info in metadatos[filename].items():
            primary_datanode = datanode_info['leader']
            follower_datanode = datanode_info['follower']
            block_id = f'{filename}_block{i}'
            file_path = os.path.join(current_directory, block_id)
            try:
                response = requests.get(f'{primary_datanode}/block/{filename}_block{i}')
                if response.status_code != 200:
                    raise requests.exceptions.RequestException
            except requests.exceptions.RequestException:
                print(f'Error al obtener bloque {i} de {primary_datanode}, intentando con follower...')
                try:
                    response = requests.get(f'{follower_datanode}/block/{filename}_block{i}')
                except requests.exceptions.RequestException:
                    print(f'Error también en {follower_datanode}. El bloque {i} está inaccesible.')
                    return jsonify({'error': f'Bloque {i} no disponible'}), 500
            if response.status_code == 200:
                file_data += response.content
            else:
                return jsonify({'error': 'Archivo no encontrado'}), 404
        return file_data


@app.route('/ls', methods=['GET'])
@auth.login_required
def list_files():
    """Lista los archivos y carpetas en el directorio actual."""
    try:
        files = os.listdir(current_directory)
        return jsonify(files)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/cd', methods=['POST'])
@auth.login_required
def change_directory():
    """Cambia de directorio."""
    global current_directory
    directory = request.json.get('directory')
    
    new_directory = os.path.join(current_directory, directory)
    
    if os.path.isdir(new_directory):
        current_directory = new_directory
        return jsonify({'message': f'Cambiado a {new_directory}'})
    else:
        return jsonify({'error': f'El directorio {directory} no existe'}), 404


@app.route('/mkdir', methods=['POST'])
@auth.login_required
def make_directory():
    """Crea un nuevo directorio."""
    directory = request.json.get('directory')
    target_directory = os.path.join(current_directory, directory)
    
    try:
        os.makedirs(target_directory)
        return jsonify({'message': f'Directorio {directory} creado'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/rmdir', methods=['POST'])
@auth.login_required
def remove_directory():
    """Elimina un directorio."""
    directory = request.json.get('directory')
    target_directory = os.path.join(current_directory, directory)

    try:
        os.rmdir(target_directory)
        return jsonify({'message': f'Directorio {directory} eliminado'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/rm', methods=['POST'])
@auth.login_required
def remove_file():
    """Elimina un archivo."""
    filename = request.json.get('filename')
    file_path = os.path.join(current_directory, filename)

    try:
        os.remove(file_path)
        return jsonify({'message': f'Archivo {filename} eliminado'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)