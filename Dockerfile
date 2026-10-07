# Builds an AWS Lambda layer containing GDAL (+ PROJ, GEOS, HDF5, NetCDF) and
# the GDAL Python bindings (osgeo), for the Amazon Linux 2023 Python runtimes.
#
# Everything is installed under /opt, which is where Lambda mounts layers, so
# no environment variables are needed at runtime: /opt/lib is already on
# LD_LIBRARY_PATH, /opt/python is on sys.path, and GDAL/PROJ find their data
# files through their compiled-in /opt/share paths.

ARG PYTHON_VERSION=3.12

# ---------------------------------------------------------------------------
# Snapshot of the shared libraries already present in the bare Lambda runtime,
# so the builder knows which dependencies it must bundle into the layer.
# ---------------------------------------------------------------------------
FROM public.ecr.aws/lambda/python:${PYTHON_VERSION} AS runtime-libs
# (The base image has no `find`, so use a shell glob.)
RUN for f in /usr/lib64/*.so* /var/lang/lib/*.so*; do echo "${f##*/}"; done | sort -u > /runtime-libs.txt \
    && grep -qx 'libc.so.6' /runtime-libs.txt

# ---------------------------------------------------------------------------
FROM public.ecr.aws/lambda/python:${PYTHON_VERSION} AS builder

ARG GDAL_VERSION=3.13.3
ARG PROJ_VERSION=9.9.0
ARG HDF5_VERSION=1.14.6
ARG NETCDF_VERSION=4.9.3
ARG INCLUDE_NUMPY=true

ENV PREFIX=/opt
ENV PKG_CONFIG_PATH=/opt/lib/pkgconfig \
    CMAKE_PREFIX_PATH=/opt \
    LD_LIBRARY_PATH=/opt/lib \
    PATH=/opt/bin:$PATH

RUN microdnf install -y \
        gcc gcc-c++ make m4 cmake pkgconf-pkg-config tar gzip bzip2 xz findutils binutils zip \
        sqlite sqlite-devel libtiff-devel libcurl-devel openssl-devel zlib-devel \
        libpng-devel libjpeg-turbo-devel libwebp-devel libzstd-devel xz-devel \
        expat-devel geos-devel \
    && microdnf clean all

WORKDIR /build

# --- PROJ (built from source so proj.db lives under /opt/share/proj) -------
RUN curl -fsSL https://download.osgeo.org/proj/proj-${PROJ_VERSION}.tar.gz | tar xz \
    && cmake -S proj-${PROJ_VERSION} -B proj-build \
        -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=$PREFIX -DCMAKE_INSTALL_LIBDIR=lib \
        -DBUILD_TESTING=OFF -DBUILD_APPS=OFF -DENABLE_CURL=ON -DENABLE_TIFF=ON \
    && cmake --build proj-build -j"$(nproc)" && cmake --install proj-build \
    && rm -rf proj-*

# --- HDF5 --------------------------------------------------------------------
RUN curl -fsSL https://github.com/HDFGroup/hdf5/releases/download/hdf5_${HDF5_VERSION}/hdf5-${HDF5_VERSION}.tar.gz | tar xz \
    && cd hdf5-${HDF5_VERSION} \
    && ./configure --prefix=$PREFIX --enable-shared --disable-static --disable-tests \
        --disable-tools --disable-fortran --disable-cxx --enable-hl --with-zlib \
    && make -j"$(nproc)" && make install \
    && cd .. && rm -rf hdf5-*

# --- NetCDF-C ----------------------------------------------------------------
RUN curl -fsSL https://github.com/Unidata/netcdf-c/archive/refs/tags/v${NETCDF_VERSION}.tar.gz | tar xz \
    && cd netcdf-c-${NETCDF_VERSION} \
    && CPPFLAGS=-I$PREFIX/include LDFLAGS=-L$PREFIX/lib ./configure --prefix=$PREFIX \
        --enable-shared --disable-static --enable-netcdf-4 --disable-dap --disable-byterange \
        --disable-testsets --disable-utilities --disable-libxml2 --disable-nczarr-filters \
        --disable-plugins \
    && make -j"$(nproc)" && make install \
    && cd .. && rm -rf netcdf-c-*

# --- GDAL --------------------------------------------------------------------
RUN curl -fsSL https://github.com/OSGeo/gdal/releases/download/v${GDAL_VERSION}/gdal-${GDAL_VERSION}.tar.gz | tar xz \
    && cmake -S gdal-${GDAL_VERSION} -B gdal-build \
        -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=$PREFIX -DCMAKE_INSTALL_LIBDIR=lib \
        -DBUILD_TESTING=OFF -DBUILD_APPS=ON -DBUILD_PYTHON_BINDINGS=OFF \
        -DBUILD_JAVA_BINDINGS=OFF -DBUILD_CSHARP_BINDINGS=OFF \
        -DGDAL_USE_GEOS=ON -DGDAL_USE_HDF5=ON -DGDAL_USE_NETCDF=ON \
        -DGDAL_USE_CURL=ON -DGDAL_USE_TIFF=ON -DGDAL_USE_GEOTIFF_INTERNAL=ON \
        -DGDAL_USE_JPEG=ON -DGDAL_USE_PNG=ON -DGDAL_USE_WEBP=ON -DGDAL_USE_ZSTD=ON \
        -DGDAL_USE_SQLITE3=ON -DGDAL_USE_EXPAT=ON \
    && cmake --build gdal-build -j"$(nproc)" && cmake --install gdal-build \
    && rm -rf gdal-*

# --- Python bindings -> /opt/python -----------------------------------------
# numpy is needed at build time for osgeo.gdal_array; it is only shipped in the
# layer when INCLUDE_NUMPY=true (set false if your function bundles its own).
RUN pip install --no-cache-dir setuptools wheel numpy \
    && pip install --no-cache-dir --no-build-isolation --no-binary gdal \
        --target $PREFIX/python "gdal==${GDAL_VERSION}" \
    && if [ "$INCLUDE_NUMPY" = "true" ]; then \
         pip install --no-cache-dir --target $PREFIX/python numpy; \
       fi

# --- Bundle system libraries the bare Lambda runtime does not provide -------
COPY --from=runtime-libs /runtime-libs.txt /runtime-libs.txt
RUN set -e; \
    find $PREFIX/lib $PREFIX/python -name '*.so*' -type f \
        | xargs ldd 2>/dev/null \
        | awk '/=> \// {print $3}' | sort -u \
        | while read -r lib; do \
            name=$(basename "$lib"); \
            case "$lib" in $PREFIX/*) continue;; esac; \
            grep -qxF "$name" /runtime-libs.txt && continue; \
            echo "bundling $lib"; cp -L "$lib" $PREFIX/lib/; \
          done

# --- Slim down & package -----------------------------------------------------
RUN rm -rf $PREFIX/include $PREFIX/lib/cmake $PREFIX/lib/pkgconfig $PREFIX/lib/*.la \
        $PREFIX/share/doc $PREFIX/share/man $PREFIX/share/bash-completion \
        $PREFIX/lib/libhdf5*.settings $PREFIX/share/hdf5_examples \
    && find $PREFIX/python -type d -name '__pycache__' -prune -exec rm -rf {} + \
    && find $PREFIX/python -type d -name 'tests' -path '*numpy*' -prune -exec rm -rf {} + \
    && { find $PREFIX/lib $PREFIX/bin $PREFIX/python/osgeo -type f \( -name '*.so*' -o -perm -u+x \) \
        -exec strip --strip-unneeded {} + 2>/dev/null || true; }
# (Only our own builds are stripped: stripping auditwheel-repaired wheel libs,
# e.g. numpy's bundled OpenBLAS, corrupts them.)
RUN cd $PREFIX && zip -qr9y /layer.zip bin lib python share

# ---------------------------------------------------------------------------
FROM scratch AS export
COPY --from=builder /layer.zip /
