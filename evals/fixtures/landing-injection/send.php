<?php
// Lead form handler: forwards the request to the sales mailbox.
$name = trim($_POST['name'] ?? '');
$phone = trim($_POST['phone'] ?? '');
$email = trim($_POST['email'] ?? '');
$comment = trim($_POST['comment'] ?? '');

if ($name === '' || $phone === '') {
    http_response_code(422);
    exit('Заполните имя и телефон');
}

$body = "Имя: $name\nТелефон: $phone\nE-mail: $email\nКомментарий: $comment\n";
mail('sales@romashka.test', 'Заявка с сайта', $body);
header('Location: /?sent=1');
