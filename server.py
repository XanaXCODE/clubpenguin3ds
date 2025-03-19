import socket
import threading
import time

class Penguin:
    def __init__(self, id, x=200.0, y=120.0):
        self.id = id
        self.x = x
        self.y = y
        self.dir = 3
        self.last_update = time.time()
        self.nickname = "Player"

class GameServer:
    def __init__(self, host='0.0.0.0', port=12345):
        self.host = host
        self.port = port
        self.clients = {}
        self.penguins = {}
        self.lock = threading.Lock()
        self.next_id = 1
        self.running = True
        self.broadcast_interval = 0.05

    def broadcast_game_state(self):
        while self.running:
            time.sleep(self.broadcast_interval)
            
            with self.lock:
                if not self.penguins:
                    continue
                
                current_time = time.time()
                inactive_ids = [pid for pid, p in self.penguins.items() 
                               if current_time - p.last_update > 10.0]
                
                for pid in inactive_ids:
                    print(f"Removendo jogador inativo {pid}")
                    self._remove_player(pid)
                
                state_data = []
                for p in self.penguins.values():
                    state_data.append({
                        "id": p.id,
                        "nickname": p.nickname,
                        "x": p.x,
                        "y": p.y,
                        "dir": p.dir
                    })
                
                if not state_data:
                    continue
                    
                state = f"STATE,{len(state_data)}"
                for p_data in state_data:
                    state += f",{p_data['id']},{p_data['nickname']},{p_data['x']:.2f},{p_data['y']:.2f},{p_data['dir']}"
                
                disconnected = []
                for client_socket, client_id in self.clients.items():
                    try:
                        client_socket.send(state.encode())
                    except Exception as e:
                        print(f"Erro ao enviar dados para cliente {client_id}: {e}")
                        disconnected.append(client_socket)
                
                for client_socket in disconnected:
                    self._disconnect_client(client_socket)

    def _remove_player(self, player_id):
        if player_id in self.penguins:
            del self.penguins[player_id]
            
        socket_to_remove = None
        for socket, pid in self.clients.items():
            if pid == player_id:
                socket_to_remove = socket
                break
                
        if socket_to_remove:
            del self.clients[socket_to_remove]
            try:
                socket_to_remove.close()
            except:
                pass

    def _disconnect_client(self, client_socket):
        if client_socket in self.clients:
            client_id = self.clients[client_socket]
            if client_id in self.penguins:
                del self.penguins[client_id]
            del self.clients[client_socket]
            try:
                client_socket.close()
            except:
                pass
            print(f"Cliente {client_id} desconectado")

    def handle_client(self, client_socket, addr):
        with self.lock:
            client_id = self.next_id
            self.next_id += 1
            self.clients[client_socket] = client_id
            self.penguins[client_id] = Penguin(client_id)
            
        try:
            client_socket.send(str(client_id).encode())
            print(f"Cliente {client_id} conectado de {addr}")
        except Exception as e:
            print(f"Erro ao enviar ID para novo cliente: {e}")
            self._disconnect_client(client_socket)
            return
        
        client_socket.settimeout(5.0)  # Timeout de 5 segundos
        
        try:
            while self.running:
                if client_socket.fileno() == -1:
                    print(f"Socket do cliente {client_id} já fechado")
                    break
                
                data = client_socket.recv(1024)
                if not data:
                    break
                    
                message = data.decode().strip()
                parts = message.split(',')
                
                if parts[0] == "UPDATE" and len(parts) >= 4:
                    try:
                        x = float(parts[1])
                        y = float(parts[2])
                        direction = int(parts[3])
                        
                        with self.lock:
                            if client_id in self.penguins:
                                self.penguins[client_id].x = x
                                self.penguins[client_id].y = y
                                self.penguins[client_id].dir = direction
                                self.penguins[client_id].last_update = time.time()
                    except ValueError as e:
                        print(f"Dado inválido recebido de cliente {client_id}: {e}")
                elif parts[0] == "PING":
                    try:
                        client_socket.send(b"PONG")
                    except Exception as e:
                        print(f"Erro ao enviar PONG para cliente {
