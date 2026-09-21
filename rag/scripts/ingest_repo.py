from rag_tool import main


if __name__ == "__main__":
    import sys

    sys.argv.insert(1, "ingest")
    raise SystemExit(main())
