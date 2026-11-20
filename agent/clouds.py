"""Adaptadores de nube. El agente solo usa esta interfaz:
list(path) -> [(nombre, es_carpeta)], get, put (nunca sobrescribe), mkdir.
Para sumar otra nube: crear otra clase y registrarla en make()."""
import os
import urllib.parse
import xml.etree.ElementTree as ET

import requests


class Cloud:
    name = "nube"

    def list(self, path):
        raise NotImplementedError

    def get(self, path):
        raise NotImplementedError

    def put(self, path, data, ctype="application/octet-stream", overwrite=False):
        raise NotImplementedError

    def mkdir(self, path):
        raise NotImplementedError

    def copy(self, src, dst):
        """Copia un archivo sin sobrescribir. True si se copió."""
        if self.exists(dst):
            return False
        self.mkdir(dst.rpartition("/")[0])
        return self.put(dst, self.get(src))

    def exists(self, path):
        parent, _, name = path.rpartition("/")
        try:
            return any(n == name for n, _ in self.list(parent))
        except Exception:
            return False


class WebDav(Cloud):
    """Koofr, Nextcloud, ownCloud, pCloud y cualquier WebDAV."""

    def __init__(self, name, url, user, password, root=""):
        self.name = name
        self.base = url.rstrip("/")
        self.root = root.strip("/")
        self.s = requests.Session()
        self.s.auth = (user, password)
        self.s.headers["User-Agent"] = "MiBibliotecaAgente/1.0"

    def _url(self, path):
        parts = [p for p in (self.root + "/" + path).split("/") if p]
        return self.base + "/" + "/".join(urllib.parse.quote(p) for p in parts)

    def list(self, path):
        r = self.s.request("PROPFIND", self._url(path), headers={"Depth": "1"}, timeout=60)
        if r.status_code == 404:
            return []
        if r.status_code in (401, 403):
            raise RuntimeError("Credenciales de la nube incorrectas")
        r.raise_for_status()
        out = []
        me = urllib.parse.unquote(urllib.parse.urlparse(self._url(path)).path).rstrip("/")
        for resp in ET.fromstring(r.content).iter("{DAV:}response"):
            href = resp.find("{DAV:}href")
            if href is None:
                continue
            p = urllib.parse.unquote(urllib.parse.urlparse(href.text).path)
            if p.rstrip("/") == me:
                continue
            isdir = resp.find(".//{DAV:}collection") is not None
            out.append((p.rstrip("/").rsplit("/", 1)[-1], isdir))
        return out

    def get(self, path):
        r = self.s.get(self._url(path), timeout=120)
        r.raise_for_status()
        return r.content

    def mkdir(self, path):
        acc = ""
        for seg in [p for p in path.split("/") if p]:
            acc += "/" + seg
            self.s.request("MKCOL", self._url(acc), timeout=60)

    def copy(self, src, dst):
        if self.exists(dst):
            return False
        self.mkdir(dst.rpartition("/")[0])
        r = self.s.request("COPY", self._url(src), headers={"Destination": self._url(dst), "Overwrite": "F"}, timeout=300)
        if r.status_code in (201, 204):
            return True
        return Cloud.copy(self, src, dst)

    def put(self, path, data, ctype="application/octet-stream", overwrite=False):
        if not overwrite and self.exists(path):
            return False
        self.mkdir(path.rpartition("/")[0])
        r = self.s.put(self._url(path), data=data, headers={"Content-Type": ctype}, timeout=300)
        return r.status_code in (200, 201, 204)


class Local(Cloud):
    """Carpeta local (para probar sin nube)."""

    def __init__(self, name, root):
        self.name = name
        self.root = root

    def _p(self, path):
        return os.path.join(self.root, *[p for p in path.split("/") if p])

    def list(self, path):
        p = self._p(path)
        if not os.path.isdir(p):
            return []
        return [(n, os.path.isdir(os.path.join(p, n))) for n in sorted(os.listdir(p))]

    def get(self, path):
        with open(self._p(path), "rb") as f:
            return f.read()

    def mkdir(self, path):
        os.makedirs(self._p(path), exist_ok=True)

    def put(self, path, data, ctype="", overwrite=False):
        p = self._p(path)
        if os.path.exists(p) and not overwrite:
            return False
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(data)
        return True


def make(cfg):
    t = cfg.get("type", "webdav")
    if t == "webdav":
        return WebDav(cfg["name"], cfg["url"], cfg["user"], cfg["password"], cfg.get("root", ""))
    if t == "local":
        return Local(cfg["name"], cfg["root"])
    raise ValueError("Tipo de nube desconocido: " + t)
