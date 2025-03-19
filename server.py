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
        self.clients = {}  # {socket: client_id}
        self.penguins = {}  # {client_id: Penguin}
        self.lock = threading.Lock()
        self.next_id = 1
        self.running = True
        self.broadcast_interval = 0.05
        self.pending_messages = {}  # {client_id: [{'data': str, 'timestamp': float}]}
        self.message_timeout = 5.0  # Timeout de 5 segundos

    def broadcast_game_state(self):
        while self.running:
            time.sleep(self.broadcast_interval)
            with self.lock:
                if not self.penguins:
                    continue

                current_time = time.time()
                # Verificar timeouts e enviar mensagens pendentes
                for client_id, messages in self.pending_messages.items():
                    # Remover mensagens expiradas
                    messages[:] = [msg for msg in messages if current_time - msg['timestamp'] < self.message_timeout]
                    if not messages:
                        continue
                    # Enviar a primeira mensagem pendente
                    msg = messages[0]
                    try:
                        client_socket = next(s for s, cid in self.clients.items() if cid == client_id)
                        client_socket.send(msg['data'].encode())
                    except Exception as e:
                        print(f"Erro ao enviar mensagem pendente para cliente {client_id}: {e}")
                        self._remove_player(client_id)

                # Enviar estado do jogo
                state_data = [
                    {"id": p.id, "nickname": p.nickname, "x": p.x, "y": p.y, "dir": p.dir}
                    for p in self.penguins.values()
                ]
                if not state_data:
                    continue

                state = f"STATE,{len(state_data)}"
                for p_data in state_data:
                    state += f",{p_data['id']},{p_data['nickname']},{p_data['x']:.2f},{p_data['y']:.2f},{p_data['dir']}"
                state += "\n"

                disconnected = []
                for client_socket, _ in self.clients.items():
                    try:
                        client_socket.send(state.encode())
                    except Exception as e:
                        print(f"Erro ao enviar estado para cliente: {e}")
                        disconnected.append(client_socket)
                for client_socket in disconnected:
                    self._disconnect_client(client_socket)

    def _remove_player(self, player_id):
        if player_id in self.penguins:
            del self.penguins[player_id]
        if player_id in self.pending_messages:
            del self.pending_messages[player_id]
        socket_to_remove = next((s for s, pid in self.clients.items() if pid == player_id), None)
        if socket_to_remove:
            del self.clients[socket_to_remove]
            try:
                socket_to_remove.close()
            except:
                pass

    def _disconnect_client(self, client_socket):
        if client_socket in self.clients:
            client_id = self.clients[client_socket]
            self._remove_player(client_id)
            print(f"Cliente {client_id} desconectado")

    def handle_client(self, client_socket, addr):
        with self.lock:
            client_id = self.next_id
            self.next_id += 1
            self.clients[client_socket] = client_id
            self.penguins[client_id] = Penguin(client_id)
            self.pending_messages[client_id] = []

        try:
            client_socket.send(str(client_id).encode())
            print(f"Cliente {client_id} conectado de {addr}")

            data = client_socket.recv(1024).decode().strip()
            if data.startswith("NICK,"):
                nickname = data.split(",", 1)[1]
                self.penguins[client_id].nickname = nickname
                print(f"Nickname do cliente {client_id}: {nickname}")

            client_socket.settimeout(5.0)
            buffer = ""

            while self.running:
                data = client_socket.recv(1024)
                if not data:
                    break

                buffer += data.decode()
                while '\n' in buffer:
                    message, buffer = buffer.split('\n', 1)
                    message = message.strip()
                    if message:
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
                            client_socket.send(b"PONG\n")
                        elif parts[0] == "CHAT" and len(parts) > 1:
                            message = ','.join(parts[1:])
                            print(f"Recebida mensagem de chat de {client_id}: {message}")
                            chat_message = f"CHAT,{client_id},{message}\n"
                            with self.lock:
                                for cid in self.penguins.keys():
                                    if cid != client_id:  # Não enviar para o remetente
                                        self.pending_messages[cid].append({
                                            'data': chat_message,
                                            'timestamp': time.time()
                                        })
                        elif parts[0] == "OK":
                            with self.lock:
                                if self.pending_messages[client_id] and len(self.pending_messages[client_id]) > 0:
                                    self.pending_messages[client_id].pop(0)
                                    print(f"Mensagem confirmada por cliente {client_id}")
        except Exception as e:
            print(f"Erro no cliente {client_id}: {e}")
        finally:
            self._disconnect_client(client_socket)

    def start(self):
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((self.host, self.port))
        server_socket.listen(10)
        print(f"Servidor iniciado em {self.host}:{self.port}")

        broadcast_thread = threading.Thread(target=self.broadcast_game_state)
        broadcast_thread.daemon = True
        broadcast_thread.start()

        while self.running:
            try:
                server_socket.settimeout(1.0)
                client_socket, addr = server_socket.accept()
                client_thread = threading.Thread(target=self.handle_client, args=(client_socket, addr))
                client_thread.daemon = True
                client_thread.start()
            except socket.timeout:
                continue
            except Exception as e:
                print(f"Erro ao aceitar conexão: {e}")
        server_socket.close()

    def stop(self):
        self.running = False

if __name__ == "__main__":
    server = GameServer()
    try:
        server.start()
    except KeyboardInterrupt:
        print("Desligando servidor...")
        server.stop()
