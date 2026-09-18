# VayuDrishti on a kind cluster

Three workloads in the `vayudrishti` namespace:

| Workload | What it is | Reachable at |
|---|---|---|
| `site` | website, model test bench (`/bench`), metrics dashboard (`/evaluation`), and `/api` forwarding | http://localhost:3001 |
| `backend` | FastAPI with the three trained models, checkpoints inside the image | http://localhost:8001/docs |
| `mongo` | accounts, sessions, audit events and the cyclone registry | inside the cluster only |

Each has its own deployment and service file. Settings that are not secret live in `configmap.yaml`;
everything secret lives in `secret.yml`, whose values are placeholders to change before first use.

## Requirements

Docker, [kind](https://kind.sigs.k8s.io) and kubectl. All commands run from the project root.

## First run

```bash
# 1. Build the two images. The backend needs Emergent's package index, because it imports
#    emergentintegrations, which is not on PyPI.
docker build -t vayudrishti-backend:local --build-arg EMERGENT_INDEX_URL=<emergent package index> backend
docker build -t vayudrishti-site:local -f hosting/docker/site.Dockerfile .

# 2. Create the cluster. This also maps ports 3001 and 8001 to this machine and mounts the bench images.
kind create cluster --config k8s/kind/cluster.yaml

# 3. Load the images into the cluster. Nothing is pulled from a registry.
kind load docker-image vayudrishti-backend:local vayudrishti-site:local --name vayudrishti

# 4. Apply the manifests. The namespace has to exist first; the rest can go in one command.
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/

# 5. Watch them come up. The backend takes a few seconds longer, because it loads three models at startup.
kubectl -n vayudrishti rollout status deployment/mongo deployment/backend deployment/site
```

Then open http://localhost:3001.

`kubectl apply -f k8s/` reads only the files directly in this folder, so the kind configuration in
`kind/` and this README are skipped.

## Loading the cyclone data

The database starts empty, so the storm registry has no storms until the data is loaded. To copy it from
the MongoDB on this machine, with the account from `secret.yml`:

```bash
mongodump --uri mongodb://127.0.0.1:27017 --db cyclone_database --archive=cyclone.archive
kubectl -n vayudrishti cp cyclone.archive "$(kubectl -n vayudrishti get pod -l app.kubernetes.io/name=mongo -o name | cut -d/ -f2):/tmp/cyclone.archive"
kubectl -n vayudrishti exec deployment/mongo -- mongorestore --archive=/tmp/cyclone.archive \
  -u vayudrishti -p change-me-before-using-this --authenticationDatabase admin
```

## After a code change

```bash
docker build -t vayudrishti-site:local -f hosting/docker/site.Dockerfile .   # or the backend image
kind load docker-image vayudrishti-site:local --name vayudrishti
kubectl -n vayudrishti rollout restart deployment/site
```

The image tag stays the same, so the restart is what picks up the new image.

## Checking and removing

```bash
kubectl -n vayudrishti get pods,svc
kubectl -n vayudrishti logs deployment/backend --tail=50
kubectl -n vayudrishti exec deployment/backend -- python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8001/api/health').read().decode())"

kubectl delete -f k8s/            # keeps the cluster
kind delete cluster --name vayudrishti
```

Deleting the namespace or the `mongo-data` claim deletes the database, including the accounts.

## Notes

- **Sign-in cookie.** It is marked secure, which browsers accept on `http://localhost`. Reach the site at
  `http://localhost:3001`, not at a machine address.
- **One backend replica.** Each replica would load its own copy of all three models, about a gigabyte of
  memory. Raising `replicas` costs that much again per pod.
- **Bench images.** The 379 MB of held-out crops are mounted from this machine through
  `kind/cluster.yaml`, not copied into the image. If that host path is wrong for your setup, every page
  still works but the bench shows no sample images.
- **Secrets.** `secret.yml` holds plain text that Kubernetes stores base64-encoded, which is not
  encryption. Anyone who can read Secrets in this namespace can read those values.
