import socket
import threading
import time
import json

# Classe para representar um pinguim no servidor
class Penguin:
    def __init__(self, id, x=200.0, y=120.0):
        self.id = id
        self.x = x
        self.y = y
        self.dir = 3
        self.last_update = time.time()
        self.nickname = "Player"
# Classe do servidor
class GameServer:
    def __init__(self, host='0.0.0.0', port=12345):
        self.host = host
        self.port = port
        self.clients = {}  # Dicionário {socket: client_id}
        self.penguins = {}  # Dicionário {client_id: Penguin}
        self.lock = threading.Lock()
        self.next_id = 1
        self.running = True
        self.broadcast_interval = 0.05  # 50ms (20 updates per second)
        
    def broadcast_game_state(self):
        """Thread dedicada para enviar atualizações de estado a todos os clientes"""
        while self.running:
            time.sleep(self.broadcast_interval)
            
            with self.lock:
                if not self.penguins:
                    continue
                
                # Remover pinguins inativos (timeout de 10 segundos)
                current_time = time.time()
                inactive_ids = [pid for pid, p in self.penguins.items() 
                            if current_time - p.last_update > 10.0]
                
                for pid in inactive_ids:
                    print(f"Removendo jogador inativo {pid}")
                    self._remove_player(pid)
                
                # Criar mensagem de estado para broadcast
                state_data = []
                for p in self.penguins.values():
                    state_data.append({
                        "id": p.id,
                        "nickname": p.nickname,  # Adicionar o nickname aqui
                        "x": p.x,
                        "y": p.y,
                        "dir": p.dir
                    })
                
                if not state_data:
                    continue
                    
                # Construir mensagem de estado
                state = f"STATE,{len(state_data)}"
                for p_data in state_data:
                    state += f",{p_data['id']},{p_data['nickname']},{p_data['x']:.2f},{p_data['y']:.2f},{p_data['dir']}"
                
                # Enviar para todos os clientes
                disconnected = []
                for client_socket, client_id in self.clients.items():
                    try:
                        client_socket.send(state.encode())
                    except Exception as e:
                        print(f"Erro ao enviar dados para cliente {client_id}: {e}")
                        disconnected.append(client_socket)
                
                # Remover clientes desconectados
                for client_socket in disconnected:
                    self._disconnect_client(client_socket)

    def _remove_player(self, player_id):
        """Remove um jogador do jogo"""
        if player_id in self.penguins:
            del self.penguins[player_id]
            
        # Encontrar e remover o socket correspondente
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
        """Desconecta um cliente e remove seu pinguim"""
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
        # Atribuir ID ao novo cliente
        with self.lock:
            client_id = self.next_id
            self.next_id += 1
            self.clients[client_socket] = client_id
            self.penguins[client_id] = Penguin(client_id)
            
        # Enviar o ID ao cliente
        try:
            client_socket.send(str(client_id).encode())
            print(f"Cliente {client_id} conectado de {addr}")
        except Exception as e:
            print(f"Erro ao enviar ID para novo cliente: {e}")
            self._disconnect_client(client_socket)
            return
        data = client_socket.recv(1024)
        if not data:
            self._disconnect_client(client_socket)
            return
        message = data.decode().strip()
        if message.startswith("NICK,"):
            nickname = message.split(',', 1)[1][:16]
            self.penguins[client_id].nickname = nickname
        # Loop principal de tratamento do cliente
        try:
            while self.running:
                data = client_socket.recv(1024)
                if not data:
                    break
                    
                message = data.decode()
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
                    # Responder pings para manter a conexão ativa
                    client_socket.send(b"PONG")
                elif parts[0] == "CHAT" and len(parts) > 1:
    # Combine all parts after the first comma as the message
                    message = ','.join(parts[1:])
                    
                    # Create a chat broadcast message
                    chat_message = f"CHAT,{client_id},{message}"
                    
                    # Broadcast to all connected clients
                    with self.lock:
                        disconnected = []
                        for socket, _ in self.clients.items():
                            try:
                                socket.send(chat_message.encode())
                            except Exception as e:
                                print(f"Error sending chat to client: {e}")
                                disconnected.append(socket)
                        
                        # Remove disconnected clients
                        for socket in disconnected:
                            self._disconnect_client(socket)
                    
        except Exception as e:
            print(f"Erro no cliente {client_id}: {e}")
        finally:
            self._disconnect_client(client_socket)

    def start(self):
        # Iniciar o servidor
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        try:
            server_socket.bind((self.host, self.port))
            server_socket.listen(10)
            print(f"Servidor iniciado em {self.host}:{self.port}")
            
            # Iniciar thread de broadcast
            broadcast_thread = threading.Thread(target=self.broadcast_game_state)
            broadcast_thread.daemon = True
            broadcast_thread.start()
            
            # Loop principal para aceitar conexões
            while self.running:
                try:
                    server_socket.settimeout(1.0)  # Timeout para permitir verificação do status running
                    client_socket, addr = server_socket.accept()
                    client_thread = threading.Thread(target=self.handle_client, args=(client_socket, addr))
                    client_thread.daemon = True
                    client_thread.start()
                except socket.timeout:
                    continue
                except Exception as e:
                    print(f"Erro ao aceitar conexão: {e}")
                    if not self.running:
                        break
                        
        except Exception as e:
            print(f"Erro ao iniciar servidor: {e}")
        finally:
            self.running = False
            server_socket.close()
            print("Servidor encerrado")

    def stop(self):
        self.running = False

if __name__ == "__main__":
    server = GameServer()
    try:
        server.start()
    except KeyboardInterrupt:
        print("Desligando servidor...")
        server.stop()