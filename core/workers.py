from rq import Worker

from .redis import rd, ocr_queue


def main():
    Worker([ocr_queue], connection=rd).work()


if __name__ == "__main__":
    main()
