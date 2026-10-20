#!/usr/bin/env bash
# Construye los paquetes .deb de Lockd (lockd y lockd-gtk) y los deja en debs/.
#
#   DEB_SNAPSHOT=true   build continuo de main: la versión lleva el sufijo
#                       +git<fecha>.<commit> y se publican alias *_latest_all.deb
#   DEB_SNAPSHOT=false  build de release (tag): la versión es la de debian/changelog
#
# Salida:
#   debs/         paquetes .deb, SHA256SUMS y archivos de la compilación
#   build.env     DEB_VERSION=<versión construida> y DEB_VERSION_URL=<la misma,
#                 con + codificado como %2B para usarla en enlaces> (dotenv para
#                 jobs posteriores)
set -euo pipefail

SNAPSHOT="${DEB_SNAPSHOT:-false}"
OUT="${DEB_OUT_DIR:-debs}"

if [ "$SNAPSHOT" = "true" ]; then
    base="$(dpkg-parsechangelog -S Version)"
    sello="$(date -u +%Y%m%d)"
    commit="$(git rev-parse --short=7 HEAD)"
    # La primera línea de debian/changelog lleva la versión entre paréntesis.
    sed -i "1s/([^)]*)/(${base}+git${sello}.${commit})/" debian/changelog
fi

version="$(dpkg-parsechangelog -S Version)"

# Un paquete nativo no admite revisión (guion) en la versión. El dpkg de
# trixie lo rechaza con error y otros más viejos solo avisan, así que se
# comprueba acá para que falle igual en local y en CI.
if [ "$(cat debian/source/format)" = "3.0 (native)" ] && [[ "$version" == *-* ]]; then
    echo "ERROR: la versión '$version' lleva guion, pero el paquete es nativo" >&2
    echo "       (debian/source/format = 3.0 (native)). Usá + en vez de -," >&2
    echo "       por ejemplo 1.0.2+parrot1." >&2
    exit 1
fi

dpkg-buildpackage -us -uc
lintian --fail-on error,warning \
    "../lockd_${version}_all.deb" "../lockd-gtk_${version}_all.deb"

mkdir -p "$OUT"
cp ../lockd_"${version}"* ../lockd-gtk_"${version}"* "$OUT"/

if [ "$SNAPSHOT" = "true" ]; then
    cp "$OUT/lockd_${version}_all.deb"     "$OUT/lockd_latest_all.deb"
    cp "$OUT/lockd-gtk_${version}_all.deb" "$OUT/lockd-gtk_latest_all.deb"
fi

(cd "$OUT" && sha256sum -- *.deb > SHA256SUMS)
{
    printf 'DEB_VERSION=%s\n' "$version"
    printf 'DEB_VERSION_URL=%s\n' "${version//+/%2B}"
} > build.env

echo "Paquetes construidos (versión $version):"
ls -l "$OUT"/*.deb
