#!/bin/bash

#
# Copyright (C) 2023 Nethesis S.r.l.
# SPDX-License-Identifier: GPL-3.0-or-later
#

# Terminate on error
set -e

# Prepare variables for later use
images=()
# The image will be pushed to GitHub container registry
repobase="${REPOBASE:-ghcr.io/nethserver}"
# Configure the image name
reponame="rag"
image_tag="${IMAGETAG:-latest}"
module_image_local="${repobase}/${reponame}"
api_image_local="${repobase}/${reponame}-api"
worker_image_local="${repobase}/${reponame}-worker"
embedder_image_local="${repobase}/${reponame}-embedder"
module_image="${module_image_local}:${image_tag}"
api_image="${api_image_local}:${image_tag}"
worker_image="${worker_image_local}:${image_tag}"
embedder_image="${embedder_image_local}:${image_tag}"
postgres_image="docker.io/library/postgres:16-alpine"
qdrant_image="docker.io/qdrant/qdrant:latest"
parser_image="docker.io/apache/tika:latest"

# Create a new empty container image
container=$(buildah from scratch)

# Reuse existing nodebuilder-ns8-rag container, to speed up builds
if ! buildah containers --format "{{.ContainerName}}" | grep -q nodebuilder-ns8-rag; then
    echo "Pulling NodeJS runtime..."
    buildah from --name nodebuilder-ns8-rag -v "${PWD}:/usr/src:Z" docker.io/library/node:24.15.0-slim
fi

echo "Build static UI files with node..."
buildah run \
    --workingdir=/usr/src/ui \
    --env="NODE_OPTIONS=--openssl-legacy-provider" \
    nodebuilder-ns8-rag \
    sh -c "corepack yarn install --no-lockfile --ignore-engines && corepack yarn build"

echo "Build runtime images..."
buildah bud -f images/rag-api/Containerfile -t "${api_image_local}" .
buildah bud -f images/rag-worker/Containerfile -t "${worker_image_local}" .
buildah bud -f images/rag-embedder/Containerfile -t "${embedder_image_local}" .

# Add imageroot directory to the container image
buildah add "${container}" imageroot /imageroot
buildah add "${container}" ui/dist /ui
# Setup the entrypoint, ask to reserve one TCP port with the label and set a rootless container
buildah config --entrypoint=/ \
    --label="org.nethserver.tcp-ports-demand=1" \
    --label="org.nethserver.rootfull=0" \
    --label="org.nethserver.images=${api_image} ${worker_image} ${embedder_image} ${postgres_image} ${qdrant_image} ${parser_image}" \
    "${container}"
# Commit the image
buildah commit "${container}" "${module_image_local}"

# Append the image URL to the images array
images+=("${module_image_local}")
images+=("${api_image_local}" "${worker_image_local}" "${embedder_image_local}")

#
# NOTICE:
#
# It is possible to build and publish multiple images.
#
# 1. create another buildah container
# 2. add things to it and commit it
# 3. append the image url to the images array
#

#
# Setup CI when pushing to Github. 
# Warning! docker::// protocol expects lowercase letters (,,)
if [[ -n "${CI}" ]]; then
    # Set output value for Github Actions
    printf "images=%s\n" "${images[*],,}" >> "${GITHUB_OUTPUT}"
else
    # Just print info for manual push
    printf "Publish the images with:\n\n"
    for image in "${images[@],,}"; do printf "  buildah push %s docker://%s\n" "${image}" "${image}" ; done
    printf "\n"
fi
