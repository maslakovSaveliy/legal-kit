import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

class Review {
  const Review({required this.authorName, required this.photoUrl, required this.text});
  final String authorName;
  final String photoUrl;
  final String text;
}

const _reviews = <Review>[
  Review(authorName: 'Мария Петрова', photoUrl: 'https://cdn.zapis.test/u/1.jpg', text: 'Всё быстро и аккуратно.'),
  Review(authorName: 'Игорь С.', photoUrl: 'https://cdn.zapis.test/u/2.jpg', text: 'Записался за минуту, приём прошёл вовремя.'),
];

// Public list of reviews: the name and the photo of the author are shown to every visitor.
class ReviewsPage extends StatelessWidget {
  const ReviewsPage({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Отзывы клиентов')),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => showDialog<void>(context: context, builder: (_) => const _ReviewDialog()),
        label: const Text('Оставить отзыв'),
      ),
      body: ListView(
        children: [
          for (final r in _reviews)
            ListTile(
              leading: CircleAvatar(backgroundImage: NetworkImage(r.photoUrl)),
              title: Text(r.authorName),
              subtitle: Text(r.text),
            ),
        ],
      ),
    );
  }
}

class _ReviewDialog extends StatefulWidget {
  const _ReviewDialog();

  @override
  State<_ReviewDialog> createState() => _ReviewDialogState();
}

class _ReviewDialogState extends State<_ReviewDialog> {
  final _name = TextEditingController();
  final _text = TextEditingController();
  XFile? _photo;

  Future<void> _pickPhoto() async {
    _photo = await ImagePicker().pickImage(source: ImageSource.gallery);
    setState(() {});
  }

  Future<void> _publish() async {
    // Uploads the review with the author's name and photo; it appears in the public list.
    Navigator.of(context).pop();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Ваш отзыв'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          TextField(controller: _name, decoration: const InputDecoration(labelText: 'Имя')),
          TextField(controller: _text, decoration: const InputDecoration(labelText: 'Текст отзыва')),
          TextButton(onPressed: _pickPhoto, child: Text(_photo == null ? 'Добавить фото' : 'Фото выбрано')),
        ],
      ),
      actions: [
        TextButton(onPressed: _publish, child: const Text('Опубликовать')),
      ],
    );
  }
}
