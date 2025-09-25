import Pyro5.api
import threading
import time
import argparse
from enum import Enum


class State(Enum):
    RELEASED = 1
    HELD = 2
    WANTED = 3


nome_processo = ''
state = State.RELEASED
HEART_BEAT_TIME = 10
TIME_HELD_SC = 20
LIST_PEERS = ['peerA', 'peerB']
ultima_vez_heartbeat = {}
peers_lock = threading.Lock()


@Pyro5.api.expose
class Peer(object):
    @Pyro5.api.oneway
    def heart_beat(self, name):
        agora = time.time()
        ultima_vez_heartbeat[name] = agora


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
    parser = argparse.ArgumentParser()
    parser.add_argument("--nome", required=True, help="Nome do processo (peer)")
    args = parser.parse_args()
    nome_processo = args.nome
    iniciar_thread_processo(nome_processo)
    time.sleep(10)

    iniciar_heartbeats()
    iniciar_monitorar_peers()

    while True:
        print("1 - Requisitar recursos")
        print("2 - Liberar recursos")
        print("3 - Listar peers ativos")
        opcao = input("Selecione uma das opções: ")

        if opcao == '3':
            ns = Pyro5.api.locate_ns()
            objetos = ns.list()
            print("")
            print("Lista de peers ativos: ")
            for nome, uri in objetos.items():
                if nome != "Pyro.NameServer":
                    print(f"Peer ativo: {nome}")
            print("")
