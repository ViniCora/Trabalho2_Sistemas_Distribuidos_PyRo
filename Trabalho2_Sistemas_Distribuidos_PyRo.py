import Pyro5.api
import threading
import time
import argparse
from enum import Enum

# SER UNICAST
        # (1) Segurança: no máximo um processo por vez pode ser executado na SC;
        # (2) Subsistência: os pedidos para entrar e sair de uma seção crítica precisam ser bem-sucedidos; 
        # (3) Ordenação: ordenar as mensagens que solicitarem a entrada na SC.
        
class State(Enum):
    RELEASED = 1
    HELD = 2
    WANTED = 3


nome_processo = ''
#On initialization state := RELEASED;
state = State.RELEASED
HEART_BEAT_TIME = 10
TIME_HELD_SC = 20
LIST_PEERS = ['peerA', 'peerB']
ultima_vez_heartbeat = {}
peers_lock = threading.Lock()
fila_request = []
count_replies = 0

@Pyro5.api.expose
class Peer(object):
    @Pyro5.api.oneway
    def heart_beat(self, name):
        agora = time.time()
        ultima_vez_heartbeat[name] = agora

    
    @Pyro5.api.oneway
    def request_entry(self,timestamp, nome):
        print(f'Recebeu o pedido de entrada do [{nome}]')
        # Se o status de todos os outros forem Release - TODOS os outros processos respondem imediatamente e o processo entra na SC
        # Se o status de algum outro for Held - então esse processo não responderá aos pedidos até que tenha terminado com a SC
        global state, fila_request
        # Adicionar a validacao por ID = Se apresentarem indicações de tempo iguais, serão ordenados de acordo com os identificadores correspondente dos processos.
        # Ver se ele vai ordenar peerA e peerB corretamente 

        # Cada peer verifica se está segurando
        if state == State.HELD:
            print(f"O {nome_processo} está em estado HELD e não pode responder a {nome} > Adicionado na Fila.")
            fila_request.append((timestamp, nome))
        elif state == State.RELEASED:
            proxy = Pyro5.api.Proxy("PYRONAME:" + nome) 
            print(f"{nome_processo} está em estado RELEASED e responde a {nome}.")
            proxy.reply_granted()
        else:
            print('erro no estado?')
            # Responder ao pedido

    @Pyro5.api.oneway
    def reply_granted(self):
        print(f'Teste')
        global count_replies
        count_replies += 1
        print(f"{nome_processo} recebeu uma permissão. Total de permissões: {count_replies}")
        if count_replies == len(LIST_PEERS) - 1:
            self.enter_SC()
            #Tem que ter timer na SC

    def request_SC(self):
        global state, count_replies, fila_request
        state = State.WANTED
        count_replies = 0
        timestamp = time.time()
        print(f"{nome_processo} está em estado WANTED e solicita permissão para entrar na SC. ts={timestamp}")

        # Unicast
        for peer in LIST_PEERS:
            if peer != nome_processo:
                try:
                    # Pede para todos para entrar na SC
                    proxy = Pyro5.api.Proxy("PYRONAME:" + peer) 
                    proxy.request_entry(timestamp, nome_processo)
                except Exception as e:
                    print(f"Falha ao enviar request_entry para {peer}: {e}")

        # Esperar até receber permissão de todos os Ppers
        # while count_replies < len(LIST_PEERS) - 1:
        #     time.sleep(0.1)

        #temporizador
        # se passar do tempo de espera ele inativa o peer
        tempo_espera = time.time() + TIME_HELD_SC
        while True:
            if count_replies == len(LIST_PEERS) - 1:
                #Replies not working yet :))))))))))))))))))))))))))))))) FUCK aushashua
                break
            if time.time() > tempo_espera:
                print(f"EXCEDEU - verificar os peers ativos e quem não respondeu - desativar ele")
                break
        
        state = State.HELD
        self.enter_SC()

    def enter_SC(self):
            global state
            print(f"{nome_processo} entrou na seção crítica.")
            time.sleep(TIME_HELD_SC)  # Simula o tempo dentro da SC
            print(f"{nome_processo} está saindo da seção crítica.")
            state = State.RELEASED
            self.exit_SC()

    def exit_SC(self):
        global state, fila_request
        state = State.RELEASED
        print(f"{nome_processo} saiu da SC")
        # Processa fila
        for ts, requester in fila_request:
            try:
                proxy = Pyro5.api.Proxy("PYRONAME:" + requester)
                proxy.reply_granted(nome_processo)
            except:
                print(f"Não foi possível enviar permissão para {requester}")
        fila_request.clear()

def start_nameserver():
    ns_uri, ns_daemon, _ = Pyro5.nameserver.start_ns(host="localhost", port=9090)
    print(f"Name Server iniciado em {ns_uri}")
    ns_daemon.requestLoop()


def localizar_nameserver():
    try:
        ns = Pyro5.api.locate_ns()
    except:
        print("NS não encontrado, criando um novo...")
        t = threading.Thread(target=start_nameserver, daemon=True)
        t.start()
        ns = Pyro5.api.locate_ns()
    return ns


def iniciar_processo(processo):
    global nome_processo;
    daemon = Pyro5.server.Daemon()
    ns = localizar_nameserver()
    nome_processo = processo
    uri = daemon.register(Peer)
    ns.register(nome_processo, uri)

    print(nome_processo + " Iniciado.")
    daemon.requestLoop()


def iniciar_thread_processo(nome_processo):
    t = threading.Thread(target=iniciar_processo, args=(nome_processo,))
    t.start()


def enviar_heartbeat_para_peer(peer):
    while True:
        with peers_lock:
            if peer not in LIST_PEERS:
                print(f"Peer {peer} foi removido da lista, thread de envio encerrada.")
                break

        inicio = time.time()
        try:
            object_name = "PYRONAME:" + peer
            proxy = Pyro5.api.Proxy(object_name)
            proxy.heart_beat(nome_processo)
        except Exception as e:
            print(f"Falha ao enviar heartbeat para {peer}: {e}")

        duracao = time.time() - inicio
        sleep_time = max(0.0, HEART_BEAT_TIME - duracao)
        time.sleep(sleep_time)


def iniciar_heartbeats():
    for peer in LIST_PEERS:
        if peer != nome_processo:
            t = threading.Thread(target=enviar_heartbeat_para_peer, args=(peer,), daemon=True)
            t.start()


def monitorar_peers():
    global LIST_PEERS
    while True:
        agora = time.time()
        with peers_lock:
            if ultima_vez_heartbeat:
                for peer in LIST_PEERS[:]:
                    ultimo = ultima_vez_heartbeat.get(peer, None)
                    if ultimo is not None and agora - ultimo > HEART_BEAT_TIME:
                        print(f"Peer {peer} não enviou heartbeat a mais de {HEART_BEAT_TIME}s, removendo da lista")
                        LIST_PEERS.remove(peer)
        time.sleep(0.5)

def iniciar_monitorar_peers():
    t_monitor = threading.Thread(target=monitorar_peers, daemon=True)
    t_monitor.start()


if __name__ == "__main__":
    # Configuração do argparse para receber o nome do processo
    parser = argparse.ArgumentParser()
    parser.add_argument("--nome", required=True, help="Nome do processo (peer)")
    args = parser.parse_args()
    nome_processo = args.nome

    iniciar_thread_processo(nome_processo)
    time.sleep(10)

    #iniciar_heartbeats()
    #iniciar_monitorar_peers()


    while True:
        print("1 - Requisitar recursos")
        print("2 - Liberar recursos")
        print("3 - Listar peers ativos")
        opcao = input("Selecione uma das opções: ")

        if opcao == '1':
            object_name = "PYRONAME:" + nome_processo 
            proxy = Pyro5.api.Proxy(object_name) 
            timeS = time.time()
            proxy.request_SC()

        if opcao == '3':
            ns = Pyro5.api.locate_ns()
            objetos = ns.list()
            print("")
            print("Lista de peers ativos: ")
            for nome, uri in objetos.items():
                if nome != "Pyro.NameServer":
                    print(f"Peer ativo: {nome}")
            print("")
