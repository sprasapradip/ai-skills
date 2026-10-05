<?php
function show($id) {
    $row = mysqli_query($db, "SELECT * FROM users WHERE id = " . $id);
    echo $_GET['name'];
    var_dump($row);
    $hash = md5($password);
    $x = @file_get_contents($f);
}
?>
