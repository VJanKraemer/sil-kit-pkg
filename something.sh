if git ls-remote --tags fork v4.0.52-rc1 | grep v4.0.52-rc1; then
    echo "create_tag=true"
else
    echo "create_tag=false"
fi
