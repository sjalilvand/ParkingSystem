 $root = "E:\ParkingSystem"
Set-Location $root
docker compose -f "$root\docker-compose.prod.yml" --env-file "$root\.env.prod" @args
